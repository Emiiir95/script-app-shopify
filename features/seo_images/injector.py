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


def _filename_from_url(image_url):
    """
    Nom de fichier actuel depuis l'URL CDN Shopify (sans le ?v=...).
    Ex: ".../products/armoire-a-bijoux-1.jpg?v=123" → "armoire-a-bijoux-1.jpg"
    """
    path = (image_url or "").split("?")[0]
    return os.path.basename(path).lower()


def build_image_updates(products):
    """
    Construit la liste des mises à jour d'images avec des noms de fichiers
    GARANTIS UNIQUES sur toute la boutique et de façon IDEMPOTENTE (relançable).

    Pourquoi : les noms de fichiers Shopify sont uniques à l'échelle de TOUTE
    la boutique (section Fichiers), pas par produit. Un nom basé sur le meta
    title provoque des collisions quand plusieurs produits ont un titre proche
    (→ "The filename provided already exists"). On base donc le nom sur le
    **handle** du produit (unique par produit chez Shopify) et on ajoute deux
    filets :
      1. Unicité globale : jamais deux images ne visent le même nom, et on évite
         un nom déjà porté par une AUTRE image de la boutique.
      2. Idempotence : une image qui porte déjà le nom cible est ignorée
         (aucun appel fileUpdate → plus d'erreur "already exists" au 2e run).

    Args:
        products : liste de dicts { handle, meta_title, images: [{gid, url}, ...] }

    Returns:
        list de dicts {gid, filename, alt, handle, position} — uniquement les
        images à réellement renommer (les déjà-correctes sont omises).
    """
    # Noms de fichiers actuels de TOUTES les images (pour ne pas voler le nom
    # d'une autre image). On mémorise aussi le nom courant par gid pour l'exclure.
    current_by_gid = {}
    all_current    = set()
    for product in products:
        for img in product.get("images", []):
            cur = _filename_from_url(img.get("url", ""))
            current_by_gid[img["gid"]] = cur
            if cur:
                all_current.add(cur)

    updates = []
    used    = set()   # noms attribués pendant CE run

    for product in products:
        handle = product["handle"]
        alt    = product["meta_title"]
        base   = slugify_title(handle) or slugify_title(alt) or "image"

        for pos, img in enumerate(product.get("images", []), start=1):
            ext     = _get_extension(img["url"])
            current = current_by_gid.get(img["gid"], "")
            target  = f"{base}-{pos}{ext}"

            # Un nom est "pris" s'il est déjà attribué ce run, ou porté par une
            # AUTRE image de la boutique (≠ le nom courant de cette image-ci).
            def _taken(name):
                return name in used or (name in all_current and name != current)

            n = 2
            while _taken(target):
                target = f"{base}-{pos}-{n}{ext}"
                n += 1

            used.add(target)

            if target == current:
                continue   # déjà correctement nommée → rien à faire (idempotent)

            updates.append({
                "gid":      img["gid"],
                "filename": target,
                "alt":      alt,
                "handle":   handle,
                "position": pos,
            })

    return updates


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
