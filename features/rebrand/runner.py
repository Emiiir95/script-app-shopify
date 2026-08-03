#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration du Rebrand produit.

Flow :
  1. Charge les remplacements depuis store_config["rebrand"]["replacements"]
  2. Récupère tous les produits avec description + SEO
  3. Calcule les modifications (sans écrire)
  4. Affiche un résumé : N produits touchés, N champs modifiés
  5. Demande confirmation
  6. Injecte produit par produit
  7. Génère le rapport CSV
"""

import sys

from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from features.rebrand.injector import (
    fetch_all_products_seo,
    compute_product_changes,
    update_product,
    generate_report,
    _FIELD_LABELS,
)
from utils.logger import log, LOG_FILE


def run(store_config, store_path):
    """
    Point d'entrée de la feature Rebrand.

    Args:
        store_config : dict { name, store_url, access_token, rebrand: { replacements } }
        store_path   : chemin absolu vers stores/{boutique}/
    """
    store_name   = store_config.get("name", "boutique")
    rebrand_cfg  = store_config.get("rebrand", {})
    replacements = rebrand_cfg.get("replacements", [])

    log("=" * 60)
    log(f"Démarrage feature Rebrand — boutique : {store_name}")
    print("=" * 60)
    print(f"  Rebrand Produit — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    if not replacements:
        print("\n[INFO] Aucun remplacement défini dans config.json.")
        print('  → Ajoutez "rebrand": { "replacements": [...] } dans votre config.json')
        print('  → Ex: { "from": "ancien-site.com", "to": "nouveau-site.com" }')
        return

    print("\n  Remplacements configurés :")
    for r in replacements:
        print(f"    {r['from']!r}  →  {r['to']!r}")

    base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(store_config["access_token"])

    # ── Fetch + analyse ───────────────────────────────────────────────────────
    print("\n[1/3] Récupération des produits...")
    products = fetch_all_products_seo(base_url, headers)
    print(f"  → {len(products)} produit(s) récupérés")

    print("\n[2/3] Analyse des modifications...")
    to_update = []
    field_counts = {"description_html": 0, "seo_title": 0, "seo_description": 0}

    for product in products:
        changes = compute_product_changes(product, replacements)
        if changes["changed"]:
            to_update.append((product, changes))
            for field in changes["fields"]:
                field_counts[field] = field_counts.get(field, 0) + 1

    if not to_update:
        print("\n  Aucun produit à modifier — rien à faire.")
        log("Rebrand — aucune modification détectée.")
        return

    print(f"\n  {len(to_update)} produit(s) à modifier :")
    for field, count in field_counts.items():
        if count:
            print(f"    • {_FIELD_LABELS[field]} : {count} produit(s)")

    print(f"\n  Aperçu (5 premiers) :")
    for product, changes in to_update[:5]:
        print(f"\n  [{product['handle']}]")
        for field, (old, new) in changes["fields"].items():
            label    = _FIELD_LABELS[field]
            old_clip = old[:80].replace("\n", " ") + ("…" if len(old) > 80 else "")
            new_clip = new[:80].replace("\n", " ") + ("…" if len(new) > 80 else "")
            print(f"    {label}")
            print(f"      avant : {old_clip}")
            print(f"      après : {new_clip}")

    print("\n" + "=" * 60)
    answer = input("Lancer le rebrand ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Rebrand — annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    # ── Injection ─────────────────────────────────────────────────────────────
    print("\n[3/3] Injection en cours...")
    ok_count   = 0
    err_count  = 0
    report_rows = []

    for product, changes in tqdm(to_update, desc="Produits mis à jour"):
        handle = product["handle"]
        try:
            update_product(product, changes, base_url, headers)
            ok_count += 1
            for field in changes["fields"]:
                report_rows.append({
                    "handle": handle,
                    "titre":  product["title"],
                    "champ":  _FIELD_LABELS[field],
                    "statut": "OK",
                    "erreur": "",
                })
        except Exception as e:
            err_count += 1
            log(f"Rebrand ÉCHEC — {handle} : {e}", "error", also_print=True)
            for field in changes["fields"]:
                report_rows.append({
                    "handle": handle,
                    "titre":  product["title"],
                    "champ":  _FIELD_LABELS[field],
                    "statut": "ERREUR",
                    "erreur": str(e),
                })

    # ── Rapport ───────────────────────────────────────────────────────────────
    if report_rows:
        generate_report(report_rows, store_path)

    # ── Résumé ────────────────────────────────────────────────────────────────
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique      : {store_name}")
    print(f"  Produits OK   : {ok_count}")
    print(f"  Produits KO   : {err_count}")
    print(f"  Logs          : {LOG_FILE}")
    print("=" * 60)
    log(f"Terminé Rebrand | OK: {ok_count} | Erreurs: {err_count}")
