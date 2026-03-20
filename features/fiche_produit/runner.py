#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration Fiche Produit.

Flow :
  1. Charge reassurance.md depuis store_path/fiche_produit/reassurance.md
  2. Fetch produits Shopify (avec images)
  3. Pour chaque produit : génère phrase, benefices, specs, titres, descriptions
     → gpt-4o pour benefices, gpt-4o-mini pour le reste (identique au JS)
  4. Sauvegarde cache fiche_produit_cache.json
  5. CSV preview → confirmation utilisateur
  6. Injection Shopify produit par produit + checkpoint
  7. Rapport CSV post-injection horodaté

Fichier contexte (par boutique) :
  stores/{boutique}/fiche_produit/reassurance.md
    → Points de réassurance injectés dans les prompts phrase, bénéfices, titres, descriptions

Config fiche_produit dans config.json :
  niche_keyword : mot-clé de la niche (utilisé dans les prompts)

Pré-requis : le Setup (feature 0) doit avoir été exécuté pour que les metaobject
definitions (benefices_produit, section_feature) et metafield definitions existent.
"""

import json
import os
import sys
import time

from datetime import datetime
from openai import OpenAI
from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from shopify.products import fetch_all_products_with_images
from features.fiche_produit.generator import (
    generate_phrase,
    generate_benefices,
    generate_titres,
    generate_descriptions,
)
from features.fiche_produit.injector import (
    generate_csv_preview,
    generate_injection_report,
    inject_product_fiche,
)
from features.seo_boost.generator import strip_html
from utils.logger import log, LOG_FILE
from utils.cost_tracker import CostTracker, estimate_cost
from utils.checkpoint import save_progress, load_progress, clear_progress

# ── Modèles et constantes ──────────────────────────────────────────────────────
MODEL_MAIN      = "gpt-4o"        # benefices
MODEL_SECONDARY = "gpt-4o-mini"   # phrase, specs, titres, descriptions

# Tokens moyens estimés par produit
_EST_MAIN_INPUT   = 500    # benefices
_EST_MAIN_OUTPUT  = 150
_EST_MINI_INPUT   = 1700   # phrase + specs + titres + descriptions
_EST_MINI_OUTPUT  = 590
_EST_MAIN_CALLS   = 1
_EST_MINI_CALLS   = 4


# ── Cache ──────────────────────────────────────────────────────────────────────

def _cache_path(store_path):
    return os.path.join(store_path, "fiche_produit_cache.json")


def _save_cache(store_path, products_data):
    cache = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "products_data": products_data,
    }
    with open(_cache_path(store_path), "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=2)
    log(f"Cache Fiche Produit sauvegardé — {len(products_data)} produit(s)")


def _load_cache(store_path):
    path = _cache_path(store_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def _clear_cache(store_path):
    path = _cache_path(store_path)
    if os.path.exists(path):
        os.remove(path)


# ── Estimation coût ────────────────────────────────────────────────────────────

def _print_cost_estimate(n_products):
    total_main_in  = _EST_MAIN_INPUT  * n_products
    total_main_out = _EST_MAIN_OUTPUT * n_products
    total_mini_in  = _EST_MINI_INPUT  * n_products
    total_mini_out = _EST_MINI_OUTPUT * n_products
    total_calls    = (_EST_MAIN_CALLS + _EST_MINI_CALLS) * n_products

    cost_main = estimate_cost(MODEL_MAIN,      total_main_in, total_main_out)
    cost_mini = estimate_cost(MODEL_SECONDARY, total_mini_in, total_mini_out)
    cost_total = cost_main + cost_mini

    print("\n" + "─" * 50)
    print("  ESTIMATION COÛT OPENAI — Fiche Produit")
    print("─" * 50)
    print(f"  Produits          : {n_products}")
    print(f"  Appels estimés    : {total_calls} ({_EST_MAIN_CALLS + _EST_MINI_CALLS}/produit)")
    print(f"  {MODEL_MAIN:<12} : ~{total_main_in:,} in / ~{total_main_out:,} out → ~${cost_main:.4f}")
    print(f"  {MODEL_SECONDARY:<12} : ~{total_mini_in:,} in / ~{total_mini_out:,} out → ~${cost_mini:.4f}")
    print(f"  Coût estimé total : ~${cost_total:.4f} USD")
    print("─" * 50)
    log(
        f"Estimation Fiche Produit — {n_products} produits | {total_calls} appels | "
        f"~${cost_total:.4f} USD ({MODEL_MAIN} + {MODEL_SECONDARY})"
    )


# ── Phase de génération ────────────────────────────────────────────────────────

def _load_reassurance(store_path):
    """
    Charge le fichier reassurance.md depuis store_path/fiche_produit/reassurance.md.
    Retourne le contenu texte brut, ou "" si absent.
    """
    path = os.path.join(store_path, "fiche_produit", "reassurance.md")
    if not os.path.exists(path):
        log("reassurance.md absent — génération sans points de réassurance.", "warning", also_print=True)
        return ""
    with open(path, encoding="utf-8") as f:
        content = f.read()
    log(f"reassurance.md chargé ({len(content)} chars)")
    return content


def _generation_phase(products, fiche_cfg, reassurance_points, openai_client, cost_tracker_main, cost_tracker_mini):
    """
    Génère phrase, benefices, specs, titres, descriptions pour chaque produit.

    Retourne :
        list de dicts {"product": ..., "content": {...}}
    """
    niche_keyword = fiche_cfg.get("niche_keyword", "")

    all_data = []

    for product in tqdm(products, desc="Génération Fiche Produit"):
        handle               = product.get("handle", "")
        product_keyword      = product.get("title", handle)
        supplier_description = strip_html(product.get("body_html", ""))

        log(f"Fiche Produit — {handle!r} | titre: {product_keyword!r}")

        # Valeurs par défaut — garantissent que le produit est toujours injecté
        phrase       = product_keyword
        benefices    = ["Qualité premium", "Confort optimal", "Design élégant"]
        titres       = [product_keyword[:60], product_keyword[:60]]
        descriptions = ["", ""]

        try:
            phrase    = generate_phrase(product_keyword, niche_keyword, reassurance_points, supplier_description, openai_client, cost_tracker_mini)
            benefices = generate_benefices(product_keyword, niche_keyword, reassurance_points, supplier_description, openai_client, cost_tracker_main)
            titres    = generate_titres(product_keyword, niche_keyword, reassurance_points, supplier_description, openai_client, cost_tracker_mini)
            descriptions = generate_descriptions(product_keyword, reassurance_points, titres, supplier_description, openai_client, cost_tracker_mini)
            log(f"SUCCÈS génération Fiche Produit — {handle}")
        except Exception as e:
            # Les générateurs ne devraient jamais lever, mais sécurité ultime
            log(f"Exception inattendue génération — {handle} | {e} — injection avec valeurs disponibles", "warning", also_print=True)

        content = {
            "phrase":       phrase,
            "benefices":    benefices,
            "titre1":       titres[0],
            "titre2":       titres[1],
            "description1": descriptions[0],
            "description2": descriptions[1],
        }
        all_data.append({"product": product, "content": content})

        time.sleep(0.5)

    return all_data


# ── Phase d'injection ──────────────────────────────────────────────────────────

def _injection_phase(all_products_data, store_path, base_url, headers, store_name,
                     cost_tracker_main, cost_tracker_mini):
    """
    CSV preview → validation utilisateur → injection Shopify → rapport.

    Returns:
        bool : True si tout OK
    """
    # CSV preview
    print("\n[GEN] Génération du CSV preview...")
    generate_csv_preview(all_products_data, store_path)

    # Validation
    print("\n" + "=" * 60)
    answer = input("Valider l'injection Shopify ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Injection Fiche Produit annulée par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée dans Shopify.")
        return False

    print("\n[INJ] Injection dans Shopify...")
    log("Début injection Fiche Produit")

    last_index, completed_handles = load_progress(store_path)
    if last_index >= 0:
        print(f"[REPRISE] Checkpoint détecté — reprise depuis le produit {last_index + 1}")

    success_count = 0
    fail_count    = 0
    injection_log = []

    for idx, entry in enumerate(tqdm(all_products_data, desc="Produits injectés")):
        product = entry["product"]
        content = entry["content"]
        handle  = product.get("handle", "")

        if handle in completed_handles:
            log(f"Skip (déjà injecté) : {handle}")
            continue

        print(f"\n  → {handle} ({idx+1}/{len(all_products_data)})")
        log(f"Injection {idx+1}/{len(all_products_data)} : {handle}")

        try:
            inject_product_fiche(product, content, base_url, headers)
            success_count += 1
            completed_handles.append(handle)
            save_progress(store_path, idx, completed_handles)
            log(f"SUCCÈS — {handle}")
            print(f"  ✓ {handle}")
            injection_log.append({"product": product, "content": content, "statut": "OK"})

        except Exception as e:
            fail_count += 1
            log(f"ÉCHEC — {handle} | {e}", "error", also_print=True)
            print(f"  ✗ {handle} — {e}")
            injection_log.append({"product": product, "content": content, "statut": "ERREUR", "erreur": str(e)})
            continue

    # Rapport post-injection
    if injection_log:
        generate_injection_report(injection_log, store_path)

    # Résumé
    cost_main = cost_tracker_main.cost_usd
    cost_mini = cost_tracker_mini.cost_usd

    log(
        f"Terminé Fiche Produit | Succès: {success_count} | Échecs: {fail_count} | "
        f"{MODEL_MAIN}: {cost_tracker_main.calls} appels ${cost_main:.4f} | "
        f"{MODEL_SECONDARY}: {cost_tracker_mini.calls} appels ${cost_mini:.4f}"
    )
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique      : {store_name}")
    print(f"  Produits OK   : {success_count}")
    print(f"  Produits KO   : {fail_count}")
    print(f"  OpenAI        : ${cost_main + cost_mini:.4f} USD total")
    print(f"    {MODEL_MAIN:<12} : {cost_tracker_main.calls} appels | ${cost_main:.4f}")
    print(f"    {MODEL_SECONDARY:<12} : {cost_tracker_mini.calls} appels | ${cost_mini:.4f}")
    print(f"  Logs          : {LOG_FILE}")
    print("=" * 60)

    if fail_count == 0:
        clear_progress(store_path)
        log("Progression effacée — tous les produits Fiche Produit traités.")

    return fail_count == 0


# ── Point d'entrée ─────────────────────────────────────────────────────────────

def run(store_config, store_path):
    """
    Point d'entrée de la feature Fiche Produit.

    Génère et injecte :
      - phrase (custom.phrase)
      - caracteristique (custom.caracteristique)
      - benefices_produit metaobject → custom.benefices
      - section_feature #1 metaobject (titre1 + desc1 + image_1) → custom.feature_1
      - section_feature #2 metaobject (titre2 + desc2 + image_2) → custom.feature_2

    Args:
        store_config : dict { name, store_url, access_token, openai_key }
        store_path   : chemin absolu vers stores/{boutique}/
    """
    store_name = store_config.get("name", "boutique")
    fiche_cfg  = store_config.get("fiche_produit", {})

    log("=" * 60)
    log(f"Démarrage feature Fiche Produit — boutique : {store_name}")
    print("=" * 60)
    print(f"  Fiche Produit — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    cost_tracker_main = CostTracker(model=MODEL_MAIN)
    cost_tracker_mini = CostTracker(model=MODEL_SECONDARY)

    # ── Vérification du cache ─────────────────────────────────────────────────
    cached = _load_cache(store_path)
    if cached:
        n_cached  = len(cached.get("products_data", []))
        cached_at = cached.get("generated_at", "date inconnue")

        print(f"\n[CACHE] {n_cached} produit(s) déjà générés le {cached_at}, en attente d'injection.")
        print("  (r) Reprendre depuis l'injection  — sans relancer OpenAI")
        print("  (n) Regénérer depuis le début     — efface le cache")
        print("  (q) Annuler")
        choice = input("\nChoix : ").strip().lower()

        if choice == "r":
            log(f"Reprise depuis le cache Fiche Produit — {n_cached} produit(s) | généré le {cached_at}")
            base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
            headers  = shopify_headers(store_config["access_token"])
            # Recharge les images avec admin_graphql_api_id (non sauvegardés dans le cache)
            print("[INFO] Rechargement des images produit...")
            fresh_products = fetch_all_products_with_images(base_url, headers)
            fresh_by_handle = {p["handle"]: p for p in fresh_products}
            for entry in cached["products_data"]:
                handle  = entry["product"].get("handle", "")
                fresh   = fresh_by_handle.get(handle, {})
                images  = fresh.get("images", [])
                entry["product"]["media_gids"] = [
                    img["admin_graphql_api_id"]
                    for img in images
                    if img.get("admin_graphql_api_id")
                ]
            success  = _injection_phase(
                cached["products_data"], store_path,
                base_url, headers, store_name,
                cost_tracker_main, cost_tracker_mini,
            )
            if success:
                _clear_cache(store_path)
            return

        elif choice == "n":
            _clear_cache(store_path)
            clear_progress(store_path)
            print("[INFO] Cache effacé — reprise depuis le début.\n")
        else:
            print("[ANNULÉ]")
            return

    # ── Chargement reassurance.md ─────────────────────────────────────────────
    print("\n[1/4] Chargement du fichier reassurance.md...")
    reassurance_points = _load_reassurance(store_path)
    if reassurance_points:
        print(f"[INFO] reassurance.md chargé ({len(reassurance_points)} chars).")
    else:
        print("[INFO] reassurance.md absent — génération sans points de réassurance.")

    # ── Connexion ─────────────────────────────────────────────────────────────
    print(f"\n[2/4] Connexion — {store_config['store_url']}")
    log(f"Session Fiche Produit — store: {store_config['store_url']} | API: {SHOPIFY_API_VERSION}")

    base_url      = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers       = shopify_headers(store_config["access_token"])
    openai_client = OpenAI(api_key=store_config["openai_key"])

    # ── Fetch produits ────────────────────────────────────────────────────────
    print("\n[3/4] Récupération des produits Shopify (avec images)...")
    products = fetch_all_products_with_images(base_url, headers)

    if not products:
        log("Aucun produit trouvé — arrêt.", "error", also_print=True)
        sys.exit(1)

    # En API 2026-01, admin_graphql_api_id sur chaque image = gid://shopify/MediaImage/...
    # Pas de GraphQL séparé nécessaire — c'est déjà dans la réponse REST.
    for product in products:
        images = product.get("images", [])
        product["media_gids"] = [
            img["admin_graphql_api_id"]
            for img in images
            if img.get("admin_graphql_api_id")
        ]

    print(f"[INFO] {len(products)} produit(s) récupérés.")
    _print_cost_estimate(len(products))

    # ── Génération OpenAI ─────────────────────────────────────────────────────
    print("\n[4/4] Génération Fiche Produit via OpenAI...")
    all_products_data = _generation_phase(
        products, fiche_cfg, reassurance_points, openai_client, cost_tracker_main, cost_tracker_mini
    )

    cost_total = cost_tracker_main.cost_usd + cost_tracker_mini.cost_usd
    print(f"\n[OPENAI] {MODEL_MAIN}: {cost_tracker_main.calls} appels ${cost_tracker_main.cost_usd:.4f} | "
          f"{MODEL_SECONDARY}: {cost_tracker_mini.calls} appels ${cost_tracker_mini.cost_usd:.4f} | "
          f"Total: ${cost_total:.4f} USD")

    if not all_products_data:
        log("Aucune donnée générée — arrêt.", "error", also_print=True)
        sys.exit(1)

    # ── Cache ─────────────────────────────────────────────────────────────────
    _save_cache(store_path, all_products_data)

    # ── Injection ─────────────────────────────────────────────────────────────
    success = _injection_phase(
        all_products_data, store_path,
        base_url, headers, store_name,
        cost_tracker_main, cost_tracker_mini,
    )
    if success:
        _clear_cache(store_path)
