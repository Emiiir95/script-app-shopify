#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
clearer.py — Retour en arrière pour Fiche Produit / Reviews.

Ces features n'écrasent pas title/handle/body_html (contrairement à SEO Boost qui a
un snapshot) : elles ne font qu'AJOUTER des metafields (+ des metaobjects). Le retour
en arrière consiste donc à SUPPRIMER les metafields produit qu'elles écrivent, ce qui
retire le contenu des pages. Les metaobjects sous-jacents restent (invisibles côté
storefront, ré-écrasés au prochain run) — non supprimés pour rester simple et sûr.
"""

from shopify.products import (
    fetch_all_products, fetch_all_product_metafields, delete_product_metafield,
)
from utils.logger import log

# Metafields produit écrits par chaque feature (namespace, key).
FEATURE_METAFIELDS = {
    "fiche_produit": [
        ("custom", "benefices"), ("custom", "feature_1"),
        ("custom", "feature_2"), ("custom", "phrase"),
    ],
    "reviews": [("custom", f"avis_client_{i}") for i in range(1, 9)]
               + [("custom", "note_globale")],
}


def clear_feature_metafields(feature, base_url, headers):
    """
    Supprime les metafields écrits par `feature` sur tous les produits.

    Returns:
        dict { feature, cleared, products, total }
    """
    keys = FEATURE_METAFIELDS.get(feature)
    if not keys:
        raise ValueError(f"Retour en arrière non supporté pour '{feature}'.")
    keyset = set(keys)

    products = fetch_all_products(base_url, headers)
    cleared = touched = 0
    for p in products:
        pid = p.get("id")
        if not pid:
            continue
        try:
            mfs = fetch_all_product_metafields(pid, base_url, headers)
        except Exception as e:
            log(f"Reset {feature} — lecture metafields échouée ({p.get('handle')}) : {e}", "warning")
            continue
        hit = False
        for m in mfs:
            if (m.get("namespace"), m.get("key")) in keyset and m.get("id"):
                try:
                    delete_product_metafield(m["id"], base_url, headers)
                    cleared += 1
                    hit = True
                except Exception as e:
                    log(f"Reset {feature} — suppression échouée ({p.get('handle')}/{m.get('key')}) : {e}", "warning")
        if hit:
            touched += 1
    return {"feature": feature, "cleared": cleared, "products": touched, "total": len(products)}
