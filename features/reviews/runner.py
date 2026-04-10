#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration complète de la feature Reviews.

Reçoit de main.py :
  - store_config : dict  { name, store_url, access_token, openai_key }
  - store_path   : str   chemin absolu vers stores/{boutique}/

Context files chargés depuis : store_path/reviews/
  - marketing.md, persona1.md, persona2.md, persona3.md

Fichiers générés dans store_path/ :
  - reviews_generated.json  → cache des reviews OpenAI (effacé après injection complète)
  - reviews_preview.csv     → aperçu avant injection
  - progress.json           → checkpoint produit par produit (effacé après succès complet)

Reprise :
  Si reviews_generated.json existe au démarrage, le script propose de sauter
  directement à l'injection sans relancer la génération OpenAI.
"""

import os
import sys
import time

from openai import OpenAI
from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from shopify.products import fetch_all_products, fetch_product_metafields, missing_review_slots
from features.reviews.generator import generate_reviews_for_product, generate_global_note
from features.reviews.injector import generate_csv_preview, generate_injection_report, inject_product_reviews
from features.reviews.prompts import build_system_prompt
from utils.logger import log, LOG_FILE
from utils.cost_tracker import CostTracker, estimate_cost
from utils.product_filter import ask_product_status
from utils.checkpoint import (
    save_progress, load_progress, clear_progress,
    save_generated_reviews, load_generated_reviews, clear_generated_reviews,
)


REVIEWS_MODEL = "gpt-4o-mini"

# Tokens moyens estimés par appel Reviews (1 appel par produit)
_REVIEWS_INPUT_BASE    = 1500  # system prompt + contexte produit
_REVIEWS_OUTPUT_PER_RV = 150   # ~150 tokens par avis généré


def _print_reviews_estimate(products_to_process):
    """Affiche l'estimation de coût OpenAI avant la génération des avis."""
    n = len(products_to_process)
    if n == 0:
        return

    avg_missing  = sum(len(e["missing_slots"]) for e in products_to_process) / n
    total_calls  = n
    total_input  = _REVIEWS_INPUT_BASE * n
    total_output = int(_REVIEWS_OUTPUT_PER_RV * avg_missing * n)
    cost         = estimate_cost(REVIEWS_MODEL, total_input, total_output)

    print("\n" + "─" * 50)
    print(f"  ESTIMATION COÛT OPENAI — Reviews")
    print("─" * 50)
    print(f"  Modèle            : {REVIEWS_MODEL}")
    print(f"  Produits          : {n}")
    print(f"  Avis moy/produit  : ~{avg_missing:.1f}")
    print(f"  Appels estimés    : {total_calls} (1/produit)")
    print(f"  Tokens entrée     : ~{total_input:,}")
    print(f"  Tokens sortie     : ~{total_output:,}")
    print(f"  Coût estimé       : ~${cost:.4f} USD")
    print("─" * 50)
    log(
        f"Estimation Reviews — {n} produits | {total_calls} appels | "
        f"~{total_input:,} tokens in | ~{total_output:,} tokens out | ~${cost:.4f} USD ({REVIEWS_MODEL})"
    )


def load_markdown_files(store_path):
    """Charge les fichiers markdown depuis store_path/reviews/."""
    context_dir = os.path.join(store_path, "reviews")
    files = ["marketing.md", "persona1.md", "persona2.md", "persona3.md"]
    contents = {}
    for f in files:
        path = os.path.join(context_dir, f)
        if not os.path.exists(path):
            log(f"Fichier manquant : {f} — les avis seront moins ciblés.", "warning", also_print=True)
            contents[f] = ""
        else:
            with open(path, "r", encoding="utf-8") as fh:
                contents[f] = fh.read()
            log(f"Fichier chargé : {f}")
    return contents


def _injection_phase(all_products_data, store_path, base_url, headers, store_name, cost_tracker):
    """
    Phase finale : CSV → validation utilisateur → injection Shopify → résumé.
    Utilisée aussi bien pour un run complet que pour une reprise depuis le cache.

    Returns:
        bool : True si tous les produits ont été injectés sans erreur
    """
    # ── CSV preview ──
    print("\n[GEN] Génération du CSV preview...")
    generate_csv_preview(all_products_data, store_path)

    # ── Validation utilisateur ──
    print("\n" + "=" * 60)
    answer = input("Valider l'import Shopify ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Import annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée dans Shopify.")
        return False

    # ── Injection ──
    print("\n[INJ] Injection dans Shopify...")
    log("Début injection Shopify")

    last_index, completed_handles = load_progress(store_path)
    if last_index >= 0:
        print(f"[REPRISE] Checkpoint détecté — reprise depuis le produit {last_index + 1}")

    success_count = 0
    fail_count    = 0
    total_reviews = 0
    injection_log = []

    for idx, entry in enumerate(tqdm(all_products_data, desc="Produits injectés")):
        product = entry["product"]
        handle  = product["handle"]

        if handle in completed_handles:
            log(f"Skip (déjà injecté) : {handle}")
            continue

        print(f"\n  → {handle} ({idx+1}/{len(all_products_data)})")
        log(f"Injection {idx+1}/{len(all_products_data)} : {handle}")

        reviews_data = {
            "note_globale":  entry["note_globale"],
            "reviews":       entry["reviews"],
            "missing_slots": entry["missing_slots"],
        }

        try:
            inject_product_reviews(product, reviews_data, base_url, headers)
            success_count += 1
            total_reviews += len(entry["reviews"])
            completed_handles.append(handle)
            save_progress(store_path, idx, completed_handles)
            log(f"SUCCÈS — {handle}")
            print(f"  ✓ {handle}")
            injection_log.append({"product": product, "entry": reviews_data, "statut": "OK"})

        except Exception as e:
            fail_count += 1
            log(f"ÉCHEC — {handle} | {e}", "error", also_print=True)
            print(f"  ✗ {handle} — {e}")
            injection_log.append({"product": product, "entry": reviews_data, "statut": "ERREUR", "erreur": str(e)})
            continue

    # ── Rapport post-injection ──
    if injection_log:
        generate_injection_report(injection_log, store_path)

    # ── Résumé ──
    log(f"Terminé | Succès: {success_count} | Échecs: {fail_count} | Avis: {total_reviews} | {cost_tracker.summary()}")
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique      : {store_name}")
    print(f"  Produits OK   : {success_count}")
    print(f"  Produits KO   : {fail_count}")
    print(f"  Avis injectés : {total_reviews}")
    if cost_tracker.calls > 0:
        print(f"  OpenAI        : {cost_tracker.calls} appels | ${cost_tracker.cost_usd:.4f} USD")
    print(f"  Logs          : {LOG_FILE}")
    print("=" * 60)

    if fail_count == 0:
        clear_progress(store_path)
        log("Progression effacée — tous les produits traités.")

    return fail_count == 0


def run(store_config, store_path):
    """
    Point d'entrée de la feature Reviews.

    Args:
        store_config : dict avec clés name, store_url, access_token, openai_key
        store_path   : chemin absolu vers le dossier de la boutique (stores/{nom}/)
    """
    store_name = store_config.get("name", "boutique")

    log("=" * 60)
    log(f"Démarrage feature Reviews — boutique : {store_name}")
    print("=" * 60)
    print(f"  Reviews — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    cost_tracker = CostTracker()

    # ── Vérification du cache de génération ──────────────────────────────────
    cached = load_generated_reviews(store_path)
    if cached:
        n_cached  = len(cached.get("products_data", []))
        cached_at = cached.get("generated_at", "date inconnue")

        print(f"\n[CACHE] {n_cached} produit(s) déjà générés le {cached_at}, en attente d'injection.")
        print("  (r) Reprendre depuis l'injection  — sans relancer OpenAI")
        print("  (n) Regénérer depuis le début     — efface le cache")
        print("  (q) Annuler")
        choice = input("\nChoix : ").strip().lower()

        if choice in ("r",):
            log(f"Reprise depuis le cache — {n_cached} produit(s) | généré le {cached_at}")
            print(f"\n[REPRISE] Connexion Shopify — {store_config['store_url']}")
            base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
            headers  = shopify_headers(store_config["access_token"])

            success = _injection_phase(
                cached["products_data"], store_path,
                base_url, headers, store_name, cost_tracker,
            )
            if success:
                clear_generated_reviews(store_path)
            return

        elif choice in ("n",):
            clear_generated_reviews(store_path)
            clear_progress(store_path)
            print("[INFO] Cache effacé — reprise depuis le début.\n")

        else:
            print("[ANNULÉ]")
            return

    # ── 1. Chargement des fichiers markdown ──────────────────────────────────
    print("\n[1/5] Chargement des fichiers markdown...")
    md_contents = load_markdown_files(store_path)

    # ── 2. Initialisation clients ─────────────────────────────────────────────
    print(f"\n[2/5] Connexion — {store_config['store_url']}")
    log(f"Session — store: {store_config['store_url']} | API: {SHOPIFY_API_VERSION}")

    base_url      = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers       = shopify_headers(store_config["access_token"])
    openai_client = OpenAI(api_key=store_config["openai_key"])
    system_prompt = build_system_prompt(md_contents)

    # ── 3. Récupération des produits ──────────────────────────────────────────
    print("\n[3/5] Récupération des produits Shopify...")
    product_status = ask_product_status()
    products = fetch_all_products(base_url, headers, status=product_status)

    if not products:
        log("Aucun produit trouvé — arrêt.", "error", also_print=True)
        sys.exit(1)

    # ── 4. Vérification des metafields existants ──────────────────────────────
    print("\n[4/5] Vérification des metafields existants...")
    products_to_process = []

    for product in tqdm(products, desc="Vérification produits"):
        metafields = fetch_product_metafields(product["id"], base_url, headers)
        missing    = missing_review_slots(metafields)
        if missing:
            products_to_process.append({"product": product, "missing_slots": missing})
            log(f"À traiter : {product['handle']} | slots manquants: {missing}")
        else:
            log(f"Ignoré (complet) : {product['handle']}")
        time.sleep(0.2)

    if not products_to_process:
        log("Tous les produits ont déjà leurs 8 avis.", also_print=True)
        sys.exit(0)

    print(f"\n[INFO] {len(products_to_process)} produit(s) à traiter.")
    _print_reviews_estimate(products_to_process)

    # ── 5. Génération des avis ────────────────────────────────────────────────
    print("\n[5/5] Génération des avis via OpenAI...")
    all_products_data = []

    for entry in tqdm(products_to_process, desc="Génération avis"):
        product       = entry["product"]
        missing_slots = entry["missing_slots"]
        handle        = product["handle"]
        n             = len(missing_slots)

        log(f"Génération OpenAI — {handle!r} | {n} avis")

        try:
            reviews = generate_reviews_for_product(
                product["title"], n, openai_client, system_prompt, cost_tracker
            )
        except Exception as e:
            log(f"ÉCHEC génération — {handle} | {e}", "error", also_print=True)
            continue

        note_globale_str, rating, count = generate_global_note()
        all_products_data.append({
            "product":       product,
            "missing_slots": missing_slots,
            "handle":        handle,
            "rating":        rating,
            "count":         count,
            "note_globale":  note_globale_str,
            "reviews":       reviews,
        })

    cost_summary = cost_tracker.summary()
    print(f"\n[OPENAI] {cost_summary}")
    log(f"Coûts OpenAI : {cost_summary}")

    if not all_products_data:
        log("Aucun avis généré — arrêt.", "error", also_print=True)
        sys.exit(1)

    # ── Sauvegarde du cache de génération ─────────────────────────────────────
    save_generated_reviews(store_path, all_products_data, store_config["store_url"])
    log(f"Cache de génération sauvegardé — {len(all_products_data)} produit(s)")

    # ── Phase d'injection ─────────────────────────────────────────────────────
    success = _injection_phase(
        all_products_data, store_path,
        base_url, headers, store_name, cost_tracker,
    )
    if success:
        clear_generated_reviews(store_path)
