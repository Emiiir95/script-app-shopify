#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Normalisation des produits Shopify.

Règles appliquées par produit/variante :
  Produit  : status → "active"
  Variante : price         → max(price, compare_at_price)
             compare_at_price → null (toujours vidé)
             taxable            → false
             inventory_policy   → "deny"
             fulfillment_service → "manual"
             requires_shipping  → true

Fonctions publiques :
  - compute_variant_changes(variant)             : calcule les changements sans écrire
  - normalize_product(product, base_url, headers): injecte les changements dans Shopify
  - generate_injection_report(log, store_path)   : CSV post-injection horodaté
"""

import csv
import os
from datetime import datetime

from shopify.client import shopify_put
from utils.logger import log


# Valeurs cibles — source de vérité unique
_TARGET_TAXABLE             = False
_TARGET_INVENTORY_POLICY    = "deny"
_TARGET_FULFILLMENT_SERVICE = "manual"
_TARGET_REQUIRES_SHIPPING   = True
_TARGET_STATUS              = "active"


def compute_variant_changes(variant):
    """
    Calcule les valeurs normalisées d'une variante sans rien écrire.

    Règle prix : si compare_at_price > price → price = compare_at_price
                 compare_at_price toujours vidé après.

    Returns:
        dict avec :
          "prix_avant", "compare_at_avant",
          "prix_apres"  (nouveau price à appliquer),
          "changed"     (bool — True si au moins un champ change)
    """
    price_str      = variant.get("price") or "0"
    compare_str    = variant.get("compare_at_price") or "0"

    try:
        price      = float(price_str)
        compare_at = float(compare_str)
    except (ValueError, TypeError):
        price      = 0.0
        compare_at = 0.0

    new_price = compare_at if compare_at > price else price

    # Détecter si quelque chose change
    price_changed   = abs(new_price - price) > 0.001
    compare_changed = compare_at != 0.0  # on vide toujours compare_at
    field_changed   = (
        bool(variant.get("taxable"))            != _TARGET_TAXABLE or
        variant.get("inventory_policy")          != _TARGET_INVENTORY_POLICY or
        variant.get("fulfillment_service")       != _TARGET_FULFILLMENT_SERVICE or
        bool(variant.get("requires_shipping"))   != _TARGET_REQUIRES_SHIPPING
    )

    return {
        "prix_avant":     price_str,
        "compare_at_avant": compare_str,
        "prix_apres":     f"{new_price:.2f}",
        "changed":        price_changed or compare_changed or field_changed,
    }


def normalize_product(product, base_url, headers):
    """
    Normalise un produit et toutes ses variantes dans Shopify.

    Étapes :
      1. PUT product → status "active" (si besoin)
      2. Pour chaque variante → PUT variant avec prix normalisé + champs cibles

    Args:
        product  : dict Shopify avec "id", "handle", "status", "variants"
        base_url : URL de base REST Shopify
        headers  : dict des headers HTTP Shopify

    Returns:
        list de dicts — une entrée par variante avec les valeurs avant/après
    """
    product_id = product["id"]
    handle     = product.get("handle", "")
    variants   = product.get("variants", [])
    variant_results = []

    # ── Étape 1 : status produit ──────────────────────────────────────────────
    if product.get("status") != _TARGET_STATUS:
        shopify_put(
            f"{base_url}/products/{product_id}.json",
            headers,
            {"product": {"id": product_id, "status": _TARGET_STATUS}},
        )
        log(f"Status produit → active — {handle}")

    # ── Étape 2 : variantes ───────────────────────────────────────────────────
    for variant in variants:
        variant_id  = variant["id"]
        sku         = variant.get("sku", "")
        changes     = compute_variant_changes(variant)

        shopify_put(
            f"{base_url}/variants/{variant_id}.json",
            headers,
            {
                "variant": {
                    "id":                  variant_id,
                    "price":               changes["prix_apres"],
                    "compare_at_price":    None,
                    "taxable":             _TARGET_TAXABLE,
                    "inventory_policy":    _TARGET_INVENTORY_POLICY,
                    "fulfillment_service": _TARGET_FULFILLMENT_SERVICE,
                    "requires_shipping":   _TARGET_REQUIRES_SHIPPING,
                }
            },
        )
        log(
            f"Variante normalisée — {handle} | SKU: {sku!r} | "
            f"prix {changes['prix_avant']} → {changes['prix_apres']} | "
            f"compare_at {changes['compare_at_avant']} → null"
        )
        variant_results.append({
            "handle":         handle,
            "titre_produit":  product.get("title", ""),
            "sku":            sku,
            "prix_avant":     changes["prix_avant"],
            "compare_at_avant": changes["compare_at_avant"],
            "prix_apres":     changes["prix_apres"],
        })

    return variant_results


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-normalisation.

    Colonnes :
        date_heure, handle, titre_produit, sku,
        prix_avant, compare_at_avant, prix_apres,
        statut, erreur

    Returns:
        str : chemin absolu du rapport généré
    """
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", f"normalisation_rapport_{timestamp}.csv")
    fieldnames = [
        "date_heure", "handle", "titre_produit", "sku",
        "prix_avant", "compare_at_avant", "prix_apres",
        "statut", "erreur",
    ]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            writer.writerow({
                "date_heure":       now_str,
                "handle":           entry.get("handle", ""),
                "titre_produit":    entry.get("titre_produit", ""),
                "sku":              entry.get("sku", ""),
                "prix_avant":       entry.get("prix_avant", ""),
                "compare_at_avant": entry.get("compare_at_avant", ""),
                "prix_apres":       entry.get("prix_apres", ""),
                "statut":           entry.get("statut", ""),
                "erreur":           entry.get("erreur", ""),
            })

    log(f"Rapport normalisation généré : {csv_path}")
    print(f"\n[RAPPORT] CSV : {csv_path}")
    return csv_path
