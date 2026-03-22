#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Injection Fiche Produit dans Shopify.

Fonctions publiques :
  - generate_csv_preview(products_data, store_path)    : CSV avant injection
  - generate_injection_report(injection_log, store_path): CSV post-injection
  - inject_product_fiche(product, content_data, base_url, headers) : injection complète

Ce que ça injecte par produit :
  1. Metaobject benefices_produit → metafield custom.benefices (metaobject_reference)
  2. Metaobject section_feature #1 (titre1 + description1 + image_1) → custom.feature_1
  3. Metaobject section_feature #2 (titre2 + description2 + image_2) → custom.feature_2
  4. Metafield custom.phrase (single_line_text_field)

Note : custom.caracteristique est injecté par la feature SEO Boost (qui lit
la description fournisseur originale avant de l'écraser avec la description SEO).
"""

import csv
import os
import time
from datetime import datetime

from shopify.metaobjects import create_metaobject_generic
from shopify.products import set_product_metafield
from utils.logger import log


def _image_gid(image_id):
    """Convertit un ID image Shopify REST en GID MediaImage (fallback uniquement)."""
    return f"gid://shopify/MediaImage/{image_id}"


def generate_csv_preview(products_data, store_path):
    """
    Génère le CSV de prévisualisation avant injection.

    Colonnes :
        handle, titre_produit, phrase, benefice_1/2/3,
        specs_apercu (100 chars), titre1, desc1_apercu (100 chars),
        titre2, desc2_apercu (100 chars), image_1_src, image_2_src

    Args:
        products_data : liste de dicts {"product": ..., "content": ...}
        store_path    : chemin absolu vers le dossier de la boutique

    Returns:
        str : chemin absolu du CSV généré
    """
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", "fiche_produit_preview.csv")
    fieldnames = [
        "handle", "titre_produit",
        "phrase",
        "benefice_1", "benefice_2", "benefice_3",
        "titre1", "desc1_apercu",
        "titre2", "desc2_apercu",
        "image_1_gid", "image_2_gid",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in products_data:
            product    = entry["product"]
            content    = entry["content"]
            media_gids = product.get("media_gids", [])
            benefices  = content.get("benefices", ["", "", ""])
            writer.writerow({
                "handle":        product.get("handle", ""),
                "titre_produit": product.get("title", ""),
                "phrase":        content.get("phrase", ""),
                "benefice_1":    benefices[0] if len(benefices) > 0 else "",
                "benefice_2":    benefices[1] if len(benefices) > 1 else "",
                "benefice_3":    benefices[2] if len(benefices) > 2 else "",
                "titre1":        content.get("titre1", ""),
                "desc1_apercu":  (content.get("description1", "") or "")[:100],
                "titre2":        content.get("titre2", ""),
                "desc2_apercu":  (content.get("description2", "") or "")[:100],
                "image_1_gid":   media_gids[0] if len(media_gids) > 0 else "",
                "image_2_gid":   media_gids[1] if len(media_gids) > 1 else "",
            })

    log(f"CSV preview Fiche Produit généré : {csv_path}")
    print(f"\n[CSV] Preview généré : {csv_path}")
    return csv_path


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-injection avec tout ce qui est entré dans Shopify.

    Colonnes :
        date_heure, handle, titre_produit, phrase, benefice_1/2/3, specs (complet),
        titre1, description1 (complet), titre2, description2 (complet),
        image_1_gid, image_2_gid, statut, erreur

    Returns:
        str : chemin absolu du rapport généré
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path  = os.path.join(store_path, "rapports", f"fiche_produit_rapport_{timestamp}.csv")
    fieldnames = [
        "date_heure", "handle", "titre_produit",
        "phrase",
        "benefice_1", "benefice_2", "benefice_3",
        "titre1", "description1",
        "titre2", "description2",
        "image_1_gid", "image_2_gid",
        "statut", "erreur",
    ]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            product   = entry["product"]
            content   = entry["content"]
            benefices = content.get("benefices", ["", "", ""])
            writer.writerow({
                "date_heure":    now_str,
                "handle":        product.get("handle", ""),
                "titre_produit": product.get("title", ""),
                "phrase":        content.get("phrase", ""),
                "benefice_1":    benefices[0] if len(benefices) > 0 else "",
                "benefice_2":    benefices[1] if len(benefices) > 1 else "",
                "benefice_3":    benefices[2] if len(benefices) > 2 else "",
                "titre1":        content.get("titre1", ""),
                "description1":  content.get("description1", ""),
                "titre2":        content.get("titre2", ""),
                "description2":  content.get("description2", ""),
                "image_1_gid":   content.get("image_1_gid", ""),
                "image_2_gid":   content.get("image_2_gid", ""),
                "statut":        entry["statut"],
                "erreur":        entry.get("erreur", ""),
            })

    log(f"Rapport injection Fiche Produit généré : {csv_path}")
    print(f"\n[RAPPORT] Injection CSV : {csv_path}")
    return csv_path


def inject_product_fiche(product, content, base_url, headers):
    """
    Injecte tous les champs Fiche Produit d'un produit dans Shopify.

    Étapes :
      1. Crée metaobject benefices_produit → SET custom.benefices
      2. Crée metaobject section_feature #1 (titre1, description1, image_1) → SET custom.feature_1
      3. Crée metaobject section_feature #2 (titre2, description2, image_2) → SET custom.feature_2
      4. SET custom.phrase
      5. SET custom.caracteristique

    Args:
        product : dict Shopify avec clés "id", "handle", "images"
        content : dict avec clés "phrase", "benefices",
                  "titre1", "description1", "titre2", "description2"
        base_url / headers : credentials Shopify

    Returns:
        dict content enrichi des GIDs injectés (image_1_gid, image_2_gid)
    """
    product_id = product["id"]
    handle     = product.get("handle", "")

    benefices     = content.get("benefices", ["", "", ""])
    phrase        = content.get("phrase", "")
    titre1        = content.get("titre1", "")
    description1  = content.get("description1", "")
    titre2        = content.get("titre2", "")
    description2  = content.get("description2", "")

    # GIDs MediaImage — priorité aux vrais GIDs GraphQL, sinon aucun (pas de fallback REST)
    media_gids  = product.get("media_gids", [])
    image_1_gid = media_gids[0] if len(media_gids) > 0 else ""
    image_2_gid = media_gids[1] if len(media_gids) > 1 else ""
    content["image_1_gid"] = image_1_gid
    content["image_2_gid"] = image_2_gid

    log(f"Début injection Fiche Produit — {handle}")

    # ── 1. benefices_produit metaobject ─────────────────────────────────────────
    bene_fields = [
        {"key": "benefice_1", "value": benefices[0] if len(benefices) > 0 else ""},
        {"key": "benefice_2", "value": benefices[1] if len(benefices) > 1 else ""},
        {"key": "benefice_3", "value": benefices[2] if len(benefices) > 2 else ""},
    ]
    bene_gid = create_metaobject_generic("benefices_produit", bene_fields, base_url, headers)
    time.sleep(0.4)

    set_product_metafield(
        product_id, "custom", "benefices",
        bene_gid, "metaobject_reference",
        base_url, headers,
    )
    log(f"benefices_produit injecté — {handle} | gid: {bene_gid}")
    time.sleep(0.4)

    # ── 2. section_feature #1 ───────────────────────────────────────────────────
    feat1_fields = [
        {"key": "titre",       "value": titre1},
        {"key": "description", "value": description1},
    ]
    if image_1_gid:
        feat1_fields.append({"key": "image", "value": image_1_gid})

    feat1_gid = create_metaobject_generic("section_feature", feat1_fields, base_url, headers)
    time.sleep(0.4)

    set_product_metafield(
        product_id, "custom", "feature_1",
        feat1_gid, "metaobject_reference",
        base_url, headers,
    )
    log(f"section_feature #1 injecté — {handle} | gid: {feat1_gid} | image: {image_1_gid or 'aucune'}")
    time.sleep(0.4)

    # ── 3. section_feature #2 ───────────────────────────────────────────────────
    feat2_fields = [
        {"key": "titre",       "value": titre2},
        {"key": "description", "value": description2},
    ]
    if image_2_gid:
        feat2_fields.append({"key": "image", "value": image_2_gid})

    feat2_gid = create_metaobject_generic("section_feature", feat2_fields, base_url, headers)
    time.sleep(0.4)

    set_product_metafield(
        product_id, "custom", "feature_2",
        feat2_gid, "metaobject_reference",
        base_url, headers,
    )
    log(f"section_feature #2 injecté — {handle} | gid: {feat2_gid} | image: {image_2_gid or 'aucune'}")
    time.sleep(0.4)

    # ── 4. phrase ────────────────────────────────────────────────────────────────
    set_product_metafield(
        product_id, "custom", "phrase",
        phrase, "single_line_text_field",
        base_url, headers,
    )
    log(f"phrase injectée — {handle} | {phrase!r}")
    time.sleep(0.4)

    log(f"Injection Fiche Produit terminée — {handle}")
    return content
