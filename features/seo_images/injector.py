#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — SEO Images : renommage fichier + alt text via GraphQL fileUpdate.

Ce module reproduit le comportement de Crush: Speed & Image Optimizer :
  - Renomme le fichier image avec le meta title slugifié
  - Met à jour l'alt text avec le meta title
  - L'URL CDN change (inévitable), mais les thèmes Liquid s'auto-mettent à jour
    car ils utilisent {{ product.images }} dynamiquement, pas des URLs hardcodées.

Fonctions publiques :
  - slugify_title(title)                                    : slug SEO depuis un titre
  - update_images_seo(image_updates, base_url, headers)     : fileUpdate batch GraphQL
  - generate_injection_report(injection_log, store_path)    : CSV post-injection horodaté
"""

import csv
import os
import re
import unicodedata
from datetime import datetime

from shopify.client import graphql_request
from utils.logger import log


def slugify_title(title):
    """
    Convertit un titre en slug SEO (identique à Shopify handle logic).
    Ex: "Arbre à Chat Sol Plafond – Balaitous" → "arbre-a-chat-sol-plafond-balaitous"
    """
    # Normalisation unicode → supprime accents
    title = unicodedata.normalize("NFKD", title)
    title = title.encode("ascii", "ignore").decode("ascii")
    title = title.lower()
    # Garde uniquement alphanumérique et tirets
    title = re.sub(r"[^\w\s-]", "", title)
    title = re.sub(r"[\s_]+", "-", title)
    title = re.sub(r"-+", "-", title).strip("-")
    return title[:80]  # max 80 chars pour garder un nom propre


def _get_extension(image_url):
    """Extrait l'extension depuis l'URL CDN Shopify (.jpg, .png, .webp, etc.)."""
    path = image_url.split("?")[0]
    ext  = os.path.splitext(path)[1].lower()
    return ext if ext in (".jpg", ".jpeg", ".png", ".webp", ".gif") else ".jpg"


def update_images_seo(image_updates, base_url, headers, max_retries=3):
    """
    Met à jour filename + alt text de plusieurs images via fileUpdate GraphQL.

    Appelle fileUpdate par batch de 10 (limite Shopify recommandée).

    Args:
        image_updates : liste de dicts {
            "gid"      : "gid://shopify/MediaImage/...",
            "filename" : "arbre-a-chat-1.jpg",
            "alt"      : "Arbre à Chat Sol Plafond – Balaitous",
            "handle"   : "arbre-a-chat-...",
            "position" : 1,
        }
        base_url : URL de base REST Shopify
        headers  : dict des headers HTTP Shopify

    Returns:
        list de dicts — résultats par image (gid, filename, alt, statut, erreur)
    """
    mutation = """
    mutation fileUpdate($files: [FileUpdateInput!]!) {
      fileUpdate(files: $files) {
        files {
          id
          alt
          ... on MediaImage {
            image { url }
          }
        }
        userErrors { field message }
      }
    }
    """

    results  = []
    batch_size = 10

    for i in range(0, len(image_updates), batch_size):
        batch = image_updates[i:i + batch_size]
        files_input = [
            {
                "id":       img["gid"],
                "alt":      img["alt"],
                "filename": img["filename"],
            }
            for img in batch
        ]

        for attempt in range(max_retries):
            try:
                data = graphql_request(base_url, headers, mutation, {"files": files_input})
                payload    = data["data"]["fileUpdate"]
                user_errors = payload.get("userErrors", [])

                if user_errors:
                    raise Exception(f"userErrors: {user_errors}")

                updated = {f["id"]: f for f in payload.get("files", [])}

                for img in batch:
                    new_url = updated.get(img["gid"], {}).get("image", {}).get("url", "")
                    results.append({
                        "handle":       img["handle"],
                        "position":     img["position"],
                        "gid":          img["gid"],
                        "filename_new": img["filename"],
                        "alt_new":      img["alt"],
                        "url_new":      new_url,
                        "statut":       "OK",
                        "erreur":       "",
                    })
                    log(f"Image SEO OK — {img['handle']} img{img['position']} | {img['filename']} | alt: {img['alt'][:40]!r}")

                break  # batch réussi

            except Exception as e:
                log(f"Erreur fileUpdate batch {i//batch_size+1} — tentative {attempt+1}/{max_retries} | {e}", "warning")
                if attempt == max_retries - 1:
                    for img in batch:
                        results.append({
                            "handle":       img["handle"],
                            "position":     img["position"],
                            "gid":          img["gid"],
                            "filename_new": img["filename"],
                            "alt_new":      img["alt"],
                            "url_new":      "",
                            "statut":       "ERREUR",
                            "erreur":       str(e),
                        })
                        log(f"Image SEO ÉCHEC — {img['handle']} img{img['position']} | {e}", "error", also_print=True)

    return results


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-injection SEO Images.

    Colonnes :
        date_heure, handle, position, gid,
        filename_new, alt_new, url_new, statut, erreur

    Returns:
        str : chemin absolu du rapport
    """
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", f"seo_images_rapport_{timestamp}.csv")
    fieldnames = [
        "date_heure", "handle", "position", "gid",
        "filename_new", "alt_new", "url_new",
        "statut", "erreur",
    ]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            writer.writerow({
                "date_heure":   now_str,
                "handle":       entry.get("handle", ""),
                "position":     entry.get("position", ""),
                "gid":          entry.get("gid", ""),
                "filename_new": entry.get("filename_new", ""),
                "alt_new":      entry.get("alt_new", ""),
                "url_new":      entry.get("url_new", ""),
                "statut":       entry.get("statut", ""),
                "erreur":       entry.get("erreur", ""),
            })

    log(f"Rapport SEO Images généré : {csv_path}")
    print(f"\n[RAPPORT] CSV : {csv_path}")
    return csv_path
