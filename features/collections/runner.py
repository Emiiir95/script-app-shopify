#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration feature Collections.

Flow :
  1. Lit les collections depuis store_config["seo_boost"]["collections"]
  2. Récupère les collections existantes sur Shopify
  3. Résumé terminal (collections à créer / à mettre à jour) + confirmation
  4. Pour chaque collection :
       a. Charge les keywords SEO pertinents depuis keywords.csv
       b. Génère description (1000+ mots), meta title, meta description via GPT
       c. Crée la collection si absente, sinon la met à jour
  5. Rapport CSV post-injection horodaté
"""

import sys

import openai
from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from features.collections.generator import (
    load_keywords_for_collection,
    generate_collection_description,
    generate_collection_meta_title,
    generate_collection_meta_desc,
)
from features.collections.injector import (
    fetch_existing_collections,
    get_handle_from_url,
    find_collection_by_handle,
    create_collection,
    update_collection,
    generate_injection_report,
)
from utils.logger import log, LOG_FILE
from utils.cost_tracker import CostTracker, estimate_cost


def run(store_config, store_path):
    """
    Point d'entrée de la feature Collections.

    Args:
        store_config : dict { name, store_url, access_token, openai_key }
        store_path   : chemin absolu vers stores/{boutique}/
    """
    store_name = store_config.get("name", "boutique")

    log("=" * 60)
    log(f"Démarrage feature Collections — boutique : {store_name}")
    print("=" * 60)
    print(f"  Collections — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    # ── Config collections ─────────────────────────────────────────────────────
    seo_config = store_config.get("seo_boost", {})
    collections_config = seo_config.get("collections", [])
    niche_keyword      = seo_config.get("niche_keyword", "")

    if not collections_config:
        print("\n[ERREUR] Aucune collection trouvée dans config.json > seo_boost > collections")
        log("Collections — aucune collection dans config.json", "error", also_print=True)
        return

    if not niche_keyword:
        print("\n[ERREUR] niche_keyword manquant dans config.json > seo_boost")
        log("Collections — niche_keyword manquant", "error", also_print=True)
        return

    # ── Shopify + OpenAI ───────────────────────────────────────────────────────
    base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(store_config["access_token"])

    openai_client = openai.OpenAI(api_key=store_config.get("openai_key", ""))
    cost_tracker  = CostTracker()

    # ── Collections existantes ─────────────────────────────────────────────────
    print("\n[1/3] Récupération des collections existantes sur Shopify...")
    existing = fetch_existing_collections(base_url, headers)
    existing_handles = {c["handle"] for c in existing}

    # ── Analyse + résumé ───────────────────────────────────────────────────────
    to_create = []
    to_update = []

    for col in collections_config:
        handle = get_handle_from_url(col["url"])
        if handle in existing_handles:
            to_update.append(col)
        else:
            to_create.append(col)

    all_collections = to_create + to_update

    print("\n" + "─" * 50)
    print("  ANALYSE — Collections")
    print("─" * 50)
    print(f"  Collections dans config.json : {len(collections_config)}")
    print(f"  Collections existantes       : {len(existing)}")
    print(f"  À créer                      : {len(to_create)}")
    print(f"  À mettre à jour (SEO)        : {len(to_update)}")
    print("─" * 50)

    if to_create:
        print("\n  Seront CRÉÉES :")
        for col in to_create:
            print(f"    + {col['name']}")
    if to_update:
        print("\n  Seront MISES À JOUR (description + meta) :")
        for col in to_update:
            print(f"    ↻ {col['name']}")

    # ── Estimation coût ────────────────────────────────────────────────────────
    # Description : gpt-4o (~1500 tokens input, ~2000 tokens output pour 1000+ mots HTML)
    # Meta title + meta desc : gpt-4o-mini
    _T_DESC_IN    = 1500
    _T_DESC_OUT   = 2000
    _T_META_IN    = 300
    _T_META_OUT   = 50

    n = len(all_collections)
    cost_desc = estimate_cost("gpt-4o",      _T_DESC_IN  * n, _T_DESC_OUT * n)
    cost_meta = estimate_cost("gpt-4o-mini", _T_META_IN  * n * 2, _T_META_OUT * n * 2)
    cost      = cost_desc + cost_meta
    total_calls = 3 * n

    print("\n" + "─" * 50)
    print("  ESTIMATION COÛT OPENAI — Collections")
    print("─" * 50)
    print(f"  Description     : gpt-4o   × {n} collections")
    print(f"  Meta title/desc : gpt-4o-mini × {n * 2} appels")
    print(f"  Appels total    : {total_calls}")
    print(f"  Coût estimé     : ~${cost:.4f} USD")
    print("─" * 50)
    log(
        f"Estimation Collections — {n} collections | {total_calls} appels | "
        f"desc gpt-4o + meta gpt-4o-mini | ~${cost:.4f} USD"
    )

    print("\n" + "=" * 60)
    answer = input("Lancer la génération et l'injection ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Collections — annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    # ── Traitement par collection ──────────────────────────────────────────────
    print("\n[2/3] Génération et injection en cours...")
    log("Début injection collections")

    injection_log = []

    for col in tqdm(all_collections, desc="Collections", unit="col"):
        col_name = col["name"]
        handle   = get_handle_from_url(col["url"])
        tags     = col.get("tags", [])
        action   = "CRÉÉE" if col in to_create else "MISE À JOUR"

        log_entry = {
            "nom":        col_name,
            "handle":     handle,
            "action":     action,
            "meta_title": "",
            "meta_desc":  "",
            "statut":     "ERREUR",
            "erreur":     "",
        }

        try:
            # Mots-clés SEO pertinents depuis keywords.csv
            seo_keywords = load_keywords_for_collection(store_path, tags)

            # Génération GPT
            description = generate_collection_description(
                col_name, niche_keyword, tags,
                seo_keywords, openai_client, cost_tracker
            )
            meta_title = generate_collection_meta_title(
                col_name, niche_keyword, tags,
                openai_client, cost_tracker, seo_keywords
            )
            meta_desc = generate_collection_meta_desc(
                col_name, niche_keyword, tags,
                openai_client, cost_tracker, seo_keywords
            )

            log_entry["meta_title"] = meta_title
            log_entry["meta_desc"]  = meta_desc

            # Injection Shopify
            if col in to_create:
                result = create_collection(col, description, meta_title, meta_desc, base_url, headers)
            else:
                existing_col = find_collection_by_handle(handle, existing)
                result = update_collection(
                    existing_col["id"], col_name, description, meta_title, meta_desc,
                    base_url, headers
                )

            if result:
                log_entry["statut"] = "OK"
                log(f"Collection OK : {col_name} ({action})")
            else:
                log_entry["statut"] = "ERREUR"
                log_entry["erreur"] = "Shopify n'a pas retourné de résultat"

        except Exception as e:
            log(f"Erreur collection '{col_name}' : {e}", "error", also_print=True)
            log_entry["erreur"] = str(e)

        injection_log.append(log_entry)

    # ── Rapport ────────────────────────────────────────────────────────────────
    print("\n[3/3] Génération du rapport...")
    generate_injection_report(injection_log, store_path)

    ok_count  = sum(1 for e in injection_log if e["statut"] == "OK")
    err_count = sum(1 for e in injection_log if e["statut"] == "ERREUR")

    # ── Résumé final ───────────────────────────────────────────────────────────
    log(f"Terminé Collections | OK: {ok_count} | Erreurs: {err_count} | Coût: {cost_tracker.summary()}")
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique         : {store_name}")
    print(f"  Collections OK   : {ok_count}")
    print(f"  Collections KO   : {err_count}")
    print(f"  {cost_tracker.summary()}")
    print(f"  Logs             : {LOG_FILE}")
    print("=" * 60)
