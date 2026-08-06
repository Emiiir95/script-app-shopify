#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Fond Studio : ajout de la nouvelle image en 1ère position Shopify.

La nouvelle image (produit sur fond uni) est ajoutée en position 1 via l'API REST
`POST /products/{id}/images.json`. Shopify décale automatiquement les images
existantes : l'ancienne 1ère devient 2ème, etc. (rien n'est supprimé).

Fonctions publiques :
  - add_first_image(product_id, image_bytes, alt, base_url, headers) : crée l'image en position 1
  - generate_injection_report(injection_log, store_path)             : CSV post-injection horodaté
"""

import base64
import csv
import os
from datetime import datetime

from shopify.client import shopify_post
from utils.logger import log


def add_first_image(product_id, image_bytes, alt, base_url, headers):
    """
    Ajoute une image en position 1 sur un produit (les autres sont décalées).

    Args:
        product_id  : id REST du produit
        image_bytes : bytes de la nouvelle image (PNG)
        alt         : texte alternatif (souvent le titre produit)

    Returns:
        dict : l'image créée (id, position, src…)
    """
    attachment = base64.b64encode(image_bytes).decode("ascii")
    url = f"{base_url}/products/{product_id}/images.json"
    payload = {"image": {"attachment": attachment, "position": 1, "alt": alt or ""}}
    data = shopify_post(url, headers, payload)
    image = data.get("image", {})
    log(f"Fond Studio — image ajoutée en position 1 sur produit {product_id} (img id: {image.get('id')})")
    return image


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-injection Fond Studio.

    Colonnes : date_heure, handle, product_id, new_image_id, statut, erreur

    Returns:
        str : chemin absolu du rapport
    """
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", f"fond_studio_rapport_{timestamp}.csv")
    fieldnames = ["date_heure", "handle", "product_id", "new_image_id", "statut", "erreur"]
    now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            writer.writerow({
                "date_heure":   now_str,
                "handle":       entry.get("handle", ""),
                "product_id":   entry.get("product_id", ""),
                "new_image_id": entry.get("new_image_id", ""),
                "statut":       entry.get("statut", ""),
                "erreur":       entry.get("erreur", ""),
            })

    log(f"Rapport Fond Studio généré : {csv_path}")
    print(f"\n[RAPPORT] CSV : {csv_path}")
    return csv_path
