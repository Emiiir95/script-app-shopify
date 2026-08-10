#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
archive.py — Archive PERMANENTE de la data générée par l'IA (jamais effacée).

Les caches de reprise (seo_boost_cache.json, etc.) sont supprimés après injection.
Ici on garde une copie horodatée et complète de tout ce qui a été généré (donc payé)
dans stores/{boutique}/generated/{feature}_{ts}.json. Contient la structure exacte
`products_data` utilisée par l'injection → 100 % re-poussable sans repayer d'OpenAI
(caractéristiques SEO et descriptions complètes incluses, contrairement aux CSV d'aperçu).
"""

import json
import os
from datetime import datetime

ARCHIVE_DIRNAME = "generated"


def _archive_dir(store_path):
    d = os.path.join(store_path, ARCHIVE_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


def save_generated(store_path, feature, products_data, store_url=""):
    """
    Archive la data générée d'une feature (jamais effacée).

    Args:
        store_path    : chemin absolu vers stores/{boutique}/
        feature       : "seo_boost" | "fiche_produit" | "reviews"
        products_data : liste des dicts générés (structure propre à la feature)
        store_url     : URL de la boutique (traçabilité)

    Returns:
        str : chemin du fichier archive créé
    """
    payload = {
        "feature":       feature,
        "generated_at":  datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "store_url":     store_url,
        "products_data": products_data,
    }
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(_archive_dir(store_path), f"{feature}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return path


def list_generated(store_path, feature=None):
    """Noms des archives disponibles (les plus récentes d'abord)."""
    d = os.path.join(store_path, ARCHIVE_DIRNAME)
    if not os.path.isdir(d):
        return []
    names = [n for n in os.listdir(d) if n.endswith(".json")
             and (not feature or n.startswith(feature + "_"))]
    return sorted(names, reverse=True)   # nom horodaté → tri = chronologique


def latest_generated(store_path, feature):
    """Charge l'archive la plus récente d'une feature (dict) ou None."""
    files = list_generated(store_path, feature)
    if not files:
        return None
    try:
        with open(os.path.join(store_path, ARCHIVE_DIRNAME, files[0]), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None
