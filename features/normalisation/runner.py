#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration Normalisation Produit.

Flow :
  1. Fetch tous les produits avec leurs variantes
  2. Analyse des changements (prix, champs variante, status)
  3. Résumé terminal + confirmation utilisateur
  4. Normalisation produit par produit
  5. Rapport CSV post-injection horodaté

Règles appliquées :
  - Variant price         → max(price, compare_at_price)
  - Variant compare_at    → null (toujours vidé)
  - Variant taxable       → false
  - Variant inventory_policy   → "deny"
  - Variant fulfillment_service → "manual"
  - Variant requires_shipping   → true
  - Product status        → "active"

Aucun appel OpenAI — feature purement Shopify API.
"""

import sys

from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from shopify.products import fetch_all_products_with_variants
from features.normalisation.injector import (
    compute_variant_changes,
    normalize_product,
    generate_injection_report,
)
from utils.logger import log, LOG_FILE


def _print_summary(products):
    """
    Affiche le résumé des changements détectés avant confirmation.
    """
    total_variants      = 0
    price_corrections   = 0
    status_corrections  = 0
    field_corrections   = 0

    for product in products:
        if product.get("status") != "active":
            status_corrections += 1
        for variant in product.get("variants", []):
            total_variants += 1
            changes = compute_variant_changes(variant)
            if changes["changed"]:
                # Distinguer correction de prix vs champs
                price_str   = variant.get("price") or "0"
                compare_str = variant.get("compare_at_price") or "0"
                try:
                    if float(compare_str) > float(price_str):
                        price_corrections += 1
                    elif float(compare_str) != 0.0:
                        price_corrections += 1  # compare_at à vider
                except (ValueError, TypeError):
                    pass
                field_corrections += 1

    print("\n" + "─" * 50)
    print("  ANALYSE — Normalisation Produit")
    print("─" * 50)
    print(f"  Produits           : {len(products)}")
    print(f"  Variantes          : {total_variants}")
    print(f"  Status à corriger  : {status_corrections}")
    print(f"  Variantes à normaliser : {field_corrections}")
    print(f"  Corrections prix   : {price_corrections}")
    print("─" * 50)


def run(store_config, store_path):
    """
    Point d'entrée de la feature Normalisation.

    Args:
        store_config : dict { name, store_url, access_token }
        store_path   : chemin absolu vers stores/{boutique}/
    """
    store_name = store_config.get("name", "boutique")

    log("=" * 60)
    log(f"Démarrage feature Normalisation — boutique : {store_name}")
    print("=" * 60)
    print(f"  Normalisation Produit — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(store_config["access_token"])

    # ── Fetch produits ────────────────────────────────────────────────────────
    print("\n[1/3] Récupération des produits Shopify...")
    products = fetch_all_products_with_variants(base_url, headers)

    if not products:
        log("Aucun produit trouvé — arrêt.", "error", also_print=True)
        sys.exit(1)

    # ── Résumé + confirmation ─────────────────────────────────────────────────
    _print_summary(products)

    print("\n[2/3] Règles qui seront appliquées :")
    print("  • price         = max(price, compare_at_price)")
    print("  • compare_at    = null")
    print("  • taxable       = false")
    print("  • inventory_policy = deny")
    print("  • fulfillment_service = manual")
    print("  • requires_shipping   = true")
    print("  • status              = active")

    print("\n" + "=" * 60)
    answer = input("Lancer la normalisation ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Normalisation annulée par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    # ── Injection ─────────────────────────────────────────────────────────────
    print("\n[3/3] Normalisation en cours...")
    log("Début normalisation Shopify")

    success_count  = 0
    fail_count     = 0
    injection_log  = []

    for product in tqdm(products, desc="Produits normalisés"):
        handle = product.get("handle", "")
        log(f"Normalisation — {handle}")

        try:
            variant_results = normalize_product(product, base_url, headers)
            success_count += 1
            for vr in variant_results:
                injection_log.append({**vr, "statut": "OK", "erreur": ""})
            log(f"SUCCÈS — {handle} | {len(variant_results)} variante(s)")

        except Exception as e:
            fail_count += 1
            log(f"ÉCHEC — {handle} | {e}", "error", also_print=True)
            print(f"  ✗ {handle} — {e}")
            for variant in product.get("variants", []):
                injection_log.append({
                    "handle":         handle,
                    "titre_produit":  product.get("title", ""),
                    "sku":            variant.get("sku", ""),
                    "prix_avant":     variant.get("price", ""),
                    "compare_at_avant": variant.get("compare_at_price", ""),
                    "prix_apres":     "",
                    "statut":         "ERREUR",
                    "erreur":         str(e),
                })

    # ── Rapport ───────────────────────────────────────────────────────────────
    if injection_log:
        generate_injection_report(injection_log, store_path)

    # ── Résumé final ──────────────────────────────────────────────────────────
    log(f"Terminé Normalisation | Succès: {success_count} | Échecs: {fail_count}")
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique      : {store_name}")
    print(f"  Produits OK   : {success_count}")
    print(f"  Produits KO   : {fail_count}")
    print(f"  Logs          : {LOG_FILE}")
    print("=" * 60)
