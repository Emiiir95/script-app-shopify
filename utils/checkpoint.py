"""
checkpoint.py — Système de sauvegarde/reprise de progression.

Le fichier progress.json est sauvegardé dans le dossier de la boutique
(store_path/progress.json) pour éviter les conflits entre boutiques.
"""

import json
import os


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
