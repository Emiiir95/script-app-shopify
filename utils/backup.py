#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backup.py — Snapshots produits pour permettre un « retour en arrière ».

Avant qu'une feature n'écrase des champs produit (title, handle, body_html…),
on sauvegarde l'état courant dans stores/{boutique}/backups/{feature}_{ts}.json,
indexé par l'ID Shopify du produit (l'ID ne change jamais → restauration fiable).

Ce module ne dépend PAS de la couche Shopify : la restauration réelle (PUT) est
faite par l'appelant (serveur backoffice) via une simple boucle sur les produits.
"""

import json
import os
from datetime import datetime

BACKUPS_DIRNAME = "backups"


def _backups_dir(store_path):
    d = os.path.join(store_path, BACKUPS_DIRNAME)
    os.makedirs(d, exist_ok=True)
    return d


def save_snapshot(store_path, feature, products, fields):
    """
    Sauvegarde l'état courant de `products` (champs `fields`) dans un JSON horodaté.

    Args:
        store_path : chemin absolu vers stores/{boutique}/
        feature    : identifiant de la feature (ex: "seo_boost")
        products   : liste de dicts produit Shopify (doivent avoir "id")
        fields     : liste des champs à sauvegarder (ex: ["title","handle","body_html"])

    Returns:
        str : chemin du fichier snapshot créé
    """
    fields = list(fields)
    snapshot = {
        "feature":    feature,
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "fields":     fields,
        "products":   [
            {"id": p.get("id"), **{f: p.get(f) for f in fields}}
            for p in products if p.get("id")
        ],
    }
    ts   = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = os.path.join(_backups_dir(store_path), f"{feature}_{ts}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)
    return path


def list_snapshots(store_path, feature=None):
    """
    Liste les snapshots disponibles (les plus récents d'abord).

    Returns:
        list de dicts { file, feature, created_at, count }
    """
    d = os.path.join(store_path, BACKUPS_DIRNAME)
    if not os.path.isdir(d):
        return []
    out = []
    # Nom horodaté YYYY-MM-DD_HH-MM-SS → tri lexicographique = chronologique
    for name in sorted(os.listdir(d), reverse=True):
        if not name.endswith(".json"):
            continue
        if feature and not name.startswith(feature + "_"):
            continue
        try:
            with open(os.path.join(d, name), encoding="utf-8") as f:
                snap = json.load(f)
        except (OSError, ValueError):
            continue
        out.append({
            "file":       name,
            "feature":    snap.get("feature"),
            "created_at": snap.get("created_at"),
            "count":      len(snap.get("products", [])),
        })
    return out


def latest_snapshot_file(store_path, feature=None):
    """Retourne le nom du snapshot le plus récent (ou None)."""
    snaps = list_snapshots(store_path, feature)
    return snaps[0]["file"] if snaps else None


def load_snapshot(store_path, filename):
    """
    Charge un snapshot par son nom de fichier (basename uniquement — anti-traversal).

    Raises:
        ValueError : nom de fichier invalide
        FileNotFoundError : snapshot absent
    """
    safe = os.path.basename(filename or "")
    if not safe.endswith(".json"):
        raise ValueError("Nom de sauvegarde invalide")
    path = os.path.join(store_path, BACKUPS_DIRNAME, safe)
    with open(path, encoding="utf-8") as f:
        return json.load(f)
