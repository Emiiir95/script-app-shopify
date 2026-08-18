#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Feature Balises : range automatiquement les produits dans les bonnes
collections, en mode SYNCHRONISATION (classement 100 % propre).

Principe : les collections de la boutique sont des smart collections « tag equals X ».
Pour classer un produit, il suffit d'écrire les bons tags dans son champ tags → Shopify
le range tout seul. Cette feature :

  1. Récupère EN DIRECT depuis Shopify TOUTES les collections (avec leurs règles de tag)
     et TOUS les produits (titre, description, type, tags actuels). On ne se fie jamais
     à la config locale de l'app, qui peut être périmée.
  2. Pour chaque produit, l'IA lit tout son contenu (+ caractéristiques) et choisit les
     collections auxquelles il appartient vraiment (plafond réglable, 0 = aucun).
  3. SYNCHRONISE le champ tags : ajoute les tags des collections choisies, retire ceux
     des collections où le produit n'est plus, préserve tous les autres tags.
  4. Aperçu → confirmation → injection (avec snapshot de secours) → rapport CSV.

Clé config : "balises" → { "max_collections": <int|0> }  (0 = aucun plafond).
"""

import sys

from openai import OpenAI
from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from shopify.products import fetch_product_metafields
from features.seo_boost.generator import strip_html
from features.balises.generator import classify_product
from features.balises.injector import (
    fetch_collections_with_rules,
    fetch_products_live,
    compute_synced_tags,
    update_product_tags,
    generate_injection_report,
)
from utils.logger import log, LOG_FILE
from utils.product_filter import ask_product_status
from utils.backup import save_snapshot
from utils.lock import StoreLock
from utils.checkpoint import save_progress, load_progress, clear_progress


def run(store_config, store_path):
    store_name = store_config.get("name", "boutique")

    log("=" * 60)
    log(f"Démarrage feature Balises — boutique : {store_name}")
    print("=" * 60)
    print(f"  Balises (rangement auto en collections) — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    openai_key = store_config.get("openai_key", "")
    if not openai_key:
        log("Clé OpenAI absente — feature IA impossible.", "error", also_print=True)
        print("[ARRÊT] Renseigne ta clé OpenAI (bouton 🔑 du backoffice) avant de lancer.")
        return

    base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(store_config["access_token"])
    openai_client = OpenAI(api_key=openai_key)

    balises_cfg     = store_config.get("balises") or {}
    max_collections = balises_cfg.get("max_collections") or 0
    try:
        max_collections = int(max_collections)
    except (TypeError, ValueError):
        max_collections = 0

    from utils.cost_tracker import CostTracker
    cost_tracker = CostTracker()

    # ── 1. Collections + produits EN DIRECT depuis Shopify ─────────────────────
    print("\n[1/4] Récupération des collections et produits (en direct Shopify)...")
    collections = fetch_collections_with_rules(base_url, headers)
    if not collections:
        log("Aucune smart collection trouvée — lance d'abord la feature Collections.",
            "error", also_print=True)
        print("[ARRÊT] Aucune collection à tag trouvée sur la boutique.")
        return

    taggable = [c for c in collections if c.get("conditions")]
    if not taggable:
        print("[ARRÊT] Aucune collection n'est basée sur un tag — rien à synchroniser.")
        log("Aucune collection tag-based — arrêt.", "warning", also_print=True)
        return
    if len(taggable) < len(collections):
        skipped = len(collections) - len(taggable)
        print(f"  ⚠ {skipped} collection(s) sans règle de tag seront ignorées (intaggables).")

    status   = ask_product_status()
    products = fetch_products_live(base_url, headers, status=status)
    if not products:
        log("Aucun produit trouvé — arrêt.", "error", also_print=True)
        return

    # ── 2. Classement IA + calcul de la synchronisation ────────────────────────
    cap_txt = "aucun plafond" if not max_collections else f"max {max_collections}/produit"
    print(f"\n[2/4] Classement IA de {len(products)} produit(s) ({cap_txt})...")

    plan    = []   # produits à modifier réellement
    skipped = []   # produits NON traités (échec IA / erreur) → listés dans le rapport
    for product in tqdm(products, desc="Classement"):
        handle = product.get("handle", "")
        try:
            # Caractéristiques (metafield custom) — best-effort, enrichit le classement.
            caract = ""
            try:
                mf = fetch_product_metafields(product["id"], base_url, headers)
                caract = mf.get("caracteristique", "") or ""
            except Exception:
                caract = ""

            product_ctx = {
                "title":            product.get("title", ""),
                "description":      strip_html(product.get("body_html", "")),
                "product_type":     product.get("product_type", ""),
                "caracteristiques": strip_html(caract),
                "tags":             product.get("tags", ""),
            }

            chosen = classify_product(
                product_ctx, taggable, openai_client, cost_tracker,
                max_collections=max_collections,
            )
            if chosen is None:
                # Panne IA sur ce produit → on ne touche PAS à ses tags (sinon on les
                # effacerait tous en mode remise à plat). Consigné dans le rapport.
                log(f"Balises — {handle!r} ignoré (classement IA échoué)", "warning")
                skipped.append({"handle": handle, "added": [], "removed": [],
                                "collections": [], "statut": "IGNORÉ",
                                "erreur": "classement IA échoué (produit intact)"})
                continue
            sync = compute_synced_tags(product.get("tags", ""), taggable, chosen)

            if sync["changed"]:
                titles = [c["title"] for c in taggable if c["handle"] in chosen]
                plan.append({
                    "product":     product,
                    "handle":      handle,
                    "new_tags":    sync["new_tags"],
                    "added":       sync["added"],
                    "removed":     sync["removed"],
                    "collections": titles,
                })
        except Exception as e:
            log(f"Balises — erreur sur {handle!r} : {e}", "error", also_print=True)
            skipped.append({"handle": handle, "added": [], "removed": [],
                            "collections": [], "statut": "IGNORÉ", "erreur": str(e)})

    # ── 3. Aperçu + confirmation ───────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("  APERÇU — Remise à plat des balises")
    print("  ⚠ Les tags de chaque produit sont REMPLACÉS par ceux des collections")
    print("    choisies (les autres tags : SEO, promo, manuels… sont supprimés).")
    print("─" * 60)
    print(f"  Produits analysés      : {len(products)}")
    print(f"  Collections (taggables): {len(taggable)}")
    print(f"  Produits à modifier    : {len(plan)}")
    print(f"  Produits ignorés (échec IA) : {len(skipped)}")
    print(f"  Coût IA                : {cost_tracker.summary()}")
    print("─" * 60)
    for p in plan[:8]:
        chg = []
        if p["added"]:
            chg.append("＋ " + ", ".join(p["added"]))
        if p["removed"]:
            chg.append("－ " + ", ".join(p["removed"]))
        print(f"  • {p['handle']:<40} {' | '.join(chg)}")
    if len(plan) > 8:
        print(f"  … et {len(plan) - 8} autre(s).")
    print("─" * 60)

    if not plan:
        if skipped:
            generate_injection_report(skipped, store_path)
            print(f"\n[OK] Rien à modifier, mais {len(skipped)} produit(s) ignoré(s) — détail dans le rapport CSV.")
        else:
            print("\n[OK] Tous les produits sont déjà dans les bonnes collections — rien à faire.")
        log(f"Balises — aucun changement (ignorés : {len(skipped)}).", also_print=True)
        return

    print("\n" + "=" * 60)
    answer = input("Remplacer TOUS les tags par ceux des collections choisies ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Balises annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    # ── 4. Injection (snapshot + verrou + reprise) ─────────────────────────────
    print("\n[3/4] Synchronisation en cours...")
    save_snapshot(store_path, "balises", [p["product"] for p in plan], ["tags"])

    _, completed = load_progress(store_path, "balises")
    completed = set(completed or [])

    store_lock = StoreLock(store_path, "balises")
    store_lock.acquire(wait_message="  ⏳ Une autre feature écrit — attente...")
    injection_log, ok, err = [], 0, 0
    try:
        for i, p in enumerate(tqdm(plan, desc="Injection")):
            handle = p["handle"]
            if handle in completed:
                continue
            entry = {"handle": handle, "added": p["added"], "removed": p["removed"],
                     "collections": p["collections"], "statut": "OK", "erreur": ""}
            try:
                update_product_tags(p["product"]["id"], p["new_tags"], base_url, headers)
                ok += 1
                log(f"Balises OK — {handle} | +{p['added']} -{p['removed']}")
            except Exception as e:
                entry["statut"], entry["erreur"] = "ERREUR", str(e)
                err += 1
                log(f"Balises ÉCHEC — {handle} | {e}", "error", also_print=True)
            injection_log.append(entry)
            completed.add(handle)
            save_progress(store_path, i, list(completed), "balises")
    finally:
        store_lock.release()

    # ── Rapport (modifiés + échecs d'écriture + ignorés) ───────────────────────
    print("\n[4/4] Génération du rapport...")
    report_rows = injection_log + skipped   # tout produit non « OK sans changement » y figure
    if report_rows:
        generate_injection_report(report_rows, store_path)
    if err == 0:
        clear_progress(store_path, "balises")

    log(f"Terminé Balises | OK: {ok} | Erreurs: {err} | Ignorés: {len(skipped)} | {cost_tracker.summary()}")
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique   : {store_name}")
    print(f"  Modifiés   : {ok}")
    print(f"  Erreurs    : {err}")
    print(f"  Ignorés    : {len(skipped)}  (échec IA — produits intacts)")
    print(f"  Coût IA    : {cost_tracker.summary()}")
    print(f"  Logs       : {LOG_FILE}")
    print("=" * 60)
