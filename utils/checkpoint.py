"""
checkpoint.py — Système de sauvegarde/reprise de progression.

Deux types de fichiers par boutique :
  progress.json          → quels produits ont été injectés (reprise post-crash)
  reviews_generated.json → reviews générées par OpenAI en attente d'injection
                           (permet de sauter la génération si elle a déjà été faite)

Les deux fichiers sont dans store_path/ pour éviter les conflits entre boutiques.
"""

import json
import os
from datetime import datetime


# ── progress.json ─────────────────────────────────────────────────────────────

def _progress_file(store_path):
    return os.path.join(store_path, "progress.json")


def save_progress(store_path, last_index, completed_handles):
    with open(_progress_file(store_path), "w", encoding="utf-8") as f:
        json.dump({"last_index": last_index, "completed": completed_handles}, f)


def load_progress(store_path):
    path = _progress_file(store_path)
    if not os.path.exists(path):
        return -1, []
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("last_index", -1), data.get("completed", [])
    except Exception:
        return -1, []


def clear_progress(store_path):
    path = _progress_file(store_path)
    if os.path.exists(path):
        os.remove(path)


# ── reviews_generated.json ────────────────────────────────────────────────────

def _generated_file(store_path):
    return os.path.join(store_path, "reviews_generated.json")


def save_generated_reviews(store_path, products_data, store_url=""):
    """
    Sauvegarde les reviews générées par OpenAI.
    Permet de reprendre depuis l'injection sans relancer la génération.

    Args:
        products_data : liste des dicts produit avec leurs reviews générées
        store_url     : URL de la boutique (pour vérification à la reprise)
    """
    data = {
        "generated_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "store_url":    store_url,
        "products_data": products_data,
    }
    with open(_generated_file(store_path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_generated_reviews(store_path):
    """
    Charge les reviews précédemment générées.
    Retourne None si le fichier n'existe pas ou est corrompu.
    """
    path = _generated_file(store_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clear_generated_reviews(store_path):
    """Supprime le cache des reviews générées."""
    path = _generated_file(store_path)
    if os.path.exists(path):
        os.remove(path)
