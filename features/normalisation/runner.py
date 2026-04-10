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
    fetch_color_pattern_map,
    create_color_pattern_metaobject,
    find_taxonomy_category_gid,
)
from utils.logger import log, LOG_FILE
from utils.product_filter import ask_product_status


def _print_summary(products, vendor):
    """
    Affiche le résumé des changements détectés avant confirmation.
    """
    total_variants      = 0
    price_corrections   = 0
    status_corrections  = 0
    field_corrections   = 0
    vendor_corrections  = 0

    for product in products:
        if product.get("status") != "active":
            status_corrections += 1
        if product.get("vendor", "") != vendor:
            vendor_corrections += 1
        for variant in product.get("variants", []):
            total_variants += 1
            changes = compute_variant_changes(variant)
            if changes["changed"]:
                price_str   = variant.get("price") or "0"
                compare_str = variant.get("compare_at_price") or "0"
                try:
                    if float(compare_str) > float(price_str):
                        price_corrections += 1
                    elif float(compare_str) != 0.0:
                        price_corrections += 1
                except (ValueError, TypeError):
                    pass
                field_corrections += 1

    print("\n" + "─" * 50)
    print("  ANALYSE — Normalisation Produit")
    print("─" * 50)
    print(f"  Produits               : {len(products)}")
    print(f"  Variantes              : {total_variants}")
    print(f"  Vendor à corriger      : {vendor_corrections}  → {vendor!r}")
    print(f"  Status à corriger      : {status_corrections}")
    print(f"  Variantes à normaliser : {field_corrections}")
    print(f"  Corrections prix       : {price_corrections}")
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
    product_status = ask_product_status()
    products = fetch_all_products_with_variants(base_url, headers, status=product_status)

    if not products:
        log("Aucun produit trouvé — arrêt.", "error", also_print=True)
        sys.exit(1)

    vendor            = store_name
    norm_config       = store_config.get("normalisation", {})
    category_name     = norm_config.get("product_category_name") or None
    category_search   = norm_config.get("product_category_search") or category_name
    category_gid      = None

    if category_search:
        print(f"\n  → Résolution catégorie Shopify : {category_name or category_search!r}...")
        category_gid = find_taxonomy_category_gid(category_search, base_url, headers)
        if category_gid:
            print(f"  → GID résolu : {category_gid}")
            log(f"Catégorie résolue : {category_search!r} → {category_gid}")
        else:
            log(f"Catégorie introuvable dans la taxonomie Shopify : {category_search!r}", "warning", also_print=True)

    # ── Résumé + confirmation ─────────────────────────────────────────────────
    _print_summary(products, vendor)

    print("\n[2/3] Règles qui seront appliquées :")
    print("  • price               = max(price, compare_at_price)")
    print("  • compare_at          = null")
    print("  • taxable             = false")
    print("  • inventory_policy    = deny")
    print("  • fulfillment_service = manual")
    print("  • requires_shipping   = true")
    status_label = "inchangé (brouillon)" if product_status == "draft" else "active"
    print(f"  • status              = {status_label}")
    print(f"  • vendor              = {vendor!r}")
    if category_name:
        if category_name:
            status = "GID résolu" if category_gid else "❌ non trouvée"
            print(f"  • catégorie           = {category_name!r}  ({status})")

    print("\n" + "=" * 60)
    answer = input("Lancer la normalisation ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Normalisation annulée par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    # ── Injection ─────────────────────────────────────────────────────────────
    print("\n[3/3] Normalisation en cours...")
    log("Début normalisation Shopify")

    # Charge la map couleur une seule fois si des produits ont l'option "Couleur"
    has_couleur = any(
        any(opt.get("name", "").strip().lower() == "couleur" for opt in p.get("options", []))
        for p in products
    )
    color_map = {}
    if has_couleur:
        print("  → Chargement des couleurs Shopify (shopify--ct-color-pattern)...")
        color_map = fetch_color_pattern_map(base_url, headers)

        # Collecter toutes les couleurs des variantes { lowercase: nom_original }
        variant_colors = {}
        for p in products:
            pos = next((o.get("position") for o in p.get("options", [])
                        if o.get("name", "").strip().lower() == "couleur"), None)
            if pos:
                for v in p.get("variants", []):
                    c = v.get(f"option{pos}", "").strip()
                    if c:
                        variant_colors.setdefault(c.lower(), c)

        missing = set(variant_colors) - set(color_map)
        print(f"  → {len(color_map)} couleur(s) existante(s) | "
              f"{len(variant_colors) - len(missing)}/{len(variant_colors)} couvertes")

        # Créer les metaobjects manquants
        if missing:
            print(f"  → Création de {len(missing)} couleur(s) manquante(s)...")
            for key in sorted(missing):
                original_name = variant_colors[key]
                try:
                    new_gid = create_color_pattern_metaobject(original_name, base_url, headers)
                    color_map[key] = new_gid
                    print(f"    ✓ {original_name!r}")
                except Exception as e:
                    log(f"Couleur {original_name!r} — création impossible : {e}", "warning", also_print=True)

    success_count  = 0
    fail_count     = 0
    injection_log  = []

    for product in tqdm(products, desc="Produits normalisés"):
        handle = product.get("handle", "")
        log(f"Normalisation — {handle}")

        try:
            keep_status = product_status is not None and product_status != "active"
            variant_results = normalize_product(product, base_url, headers, vendor, category_gid, None, color_map, keep_status=keep_status)
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
