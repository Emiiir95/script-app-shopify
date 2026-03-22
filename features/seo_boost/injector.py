#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Injection des données SEO dans Shopify pour la feature SEO Boost.

Fonctions publiques :
  - generate_csv_preview(products_data, store_path)             : génère le CSV aperçu avant injection
  - generate_injection_report(injection_log, store_path)        : rapport post-injection (ce qui est entré dans Shopify)
  - inject_product_seo(product, seo_data, base_url, headers,
                       generate_meta_desc, generate_description) : injecte le SEO d'un produit
"""

import csv
import os
from datetime import datetime

from shopify.client import shopify_put
from shopify.products import set_product_metafield
from utils.logger import log


def generate_csv_preview(products_data, store_path):
    """
    Génère le fichier CSV de prévisualisation avant injection Shopify.

    Colonnes :
        handle_original, handle_nouveau, titre_original, h1_nouveau,
        differentiator, branding_name, meta_title, meta_description,
        description_html_apercu (200 premiers chars)

    Args:
        products_data : liste de dicts, chacun contenant "product" et "seo_data"
        store_path    : chemin absolu vers le dossier de la boutique

    Returns:
        str : chemin absolu du fichier CSV généré
    """
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", "seo_boost_preview.csv")
    fieldnames = [
        "handle_original",
        "handle_nouveau",
        "titre_original",
        "h1_nouveau",
        "differentiator",
        "branding_name",
        "meta_title",
        "meta_description",
        "description_html",
    ]

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in products_data:
            product  = entry["product"]
            seo_data = entry["seo_data"]
            writer.writerow({
                "handle_original": product.get("handle", ""),
                "handle_nouveau":  seo_data.get("handle_nouveau", ""),
                "titre_original":  product.get("title", ""),
                "h1_nouveau":      seo_data.get("h1", ""),
                "differentiator":  seo_data.get("differentiator", ""),
                "branding_name":   seo_data.get("branding_name", ""),
                "meta_title":      seo_data.get("meta_title", ""),
                "meta_description": seo_data.get("meta_description", ""),
                "description_html": seo_data.get("description_html", ""),
            })

    log(f"CSV preview SEO Boost généré : {csv_path}")
    print(f"\n[CSV] Preview généré : {csv_path}")
    return csv_path


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-injection : tout ce qui a été envoyé dans Shopify,
    produit par produit, avec statut OK/ERREUR.

    Colonnes :
        date_heure, handle_original, handle_nouveau, titre_original,
        h1_nouveau, meta_title, meta_description, description_html,
        statut, erreur

    Args:
        injection_log : liste de dicts construite pendant l'injection
                        { product, seo_data, statut, erreur }
        store_path    : chemin absolu vers le dossier de la boutique

    Returns:
        str : chemin absolu du rapport généré
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path  = os.path.join(store_path, "rapports", f"seo_boost_rapport_{timestamp}.csv")

    fieldnames = [
        "date_heure",
        "handle_original",
        "handle_nouveau",
        "titre_original",
        "h1_nouveau",
        "meta_title",
        "meta_description",
        "description_html",
        "statut",
        "erreur",
    ]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            product  = entry["product"]
            seo_data = entry["seo_data"]
            writer.writerow({
                "date_heure":      now_str,
                "handle_original": product.get("handle", ""),
                "handle_nouveau":  seo_data.get("handle_nouveau", ""),
                "titre_original":  product.get("title", ""),
                "h1_nouveau":      seo_data.get("h1", ""),
                "meta_title":      seo_data.get("meta_title", ""),
                "meta_description": seo_data.get("meta_description", ""),
                "description_html": seo_data.get("description_html", ""),
                "statut":          entry["statut"],
                "erreur":          entry.get("erreur", ""),
            })

    log(f"Rapport injection SEO Boost généré : {csv_path}")
    print(f"\n[RAPPORT] Injection CSV : {csv_path}")
    return csv_path


def inject_product_seo(product, seo_data, base_url, headers, generate_meta_desc=True, generate_description=True):
    """
    Injecte les données SEO d'un produit dans Shopify.

    Étapes :
      1. PUT title + handle + body_html (si generate_description et description_html non vide)
      2. SET metafield global.title_tag (meta title)
      3. SET metafield global.description_tag (meta description) — si generate_meta_desc est True
      4. SET metafield custom.caracteristique (caractéristiques techniques HTML)

    Args:
        product              : dict avec clés "id", "handle", "title", "body_html"
        seo_data             : dict avec clés "h1", "meta_title", "handle_nouveau",
                               "meta_description", "description_html", "caracteristique"
        base_url             : URL de base REST Shopify
        headers              : dict des headers HTTP Shopify
        generate_meta_desc   : bool — si True et meta_description non vide, injecte la meta desc
        generate_description : bool — si True et description_html non vide, injecte le body_html

    Returns:
        None

    Raises:
        Exception : propagée depuis les fonctions Shopify en cas d'erreur réseau
    """
    product_id       = product["id"]
    handle_origin    = product.get("handle", "")
    h1               = seo_data.get("h1", "")
    meta_title       = seo_data.get("meta_title", "")
    handle_nouveau   = seo_data.get("handle_nouveau", "")
    meta_description = seo_data.get("meta_description", "")
    description_html = seo_data.get("description_html", "")
    caracteristique  = seo_data.get("caracteristique", "")

    log(f"Début injection SEO — {handle_origin} | h1: {h1!r} | handle_nouveau: {handle_nouveau!r}")

    # ── Étape 1 : PUT title + handle (+ body_html si activé) ─────────────────
    product_url = f"{base_url}/products/{product_id}.json"
    payload = {
        "product": {
            "id":     product_id,
            "title":  h1,
            "handle": handle_nouveau,
        }
    }
    if generate_description and description_html:
        payload["product"]["body_html"] = description_html

    shopify_put(product_url, headers, payload)
    log(f"PUT produit OK — {handle_origin} | title: {h1!r} | handle: {handle_nouveau!r}")

    # ── Étape 2 : meta title (global.title_tag) ───────────────────────────────
    set_product_metafield(
        product_id, "global", "title_tag",
        meta_title, "single_line_text_field",
        base_url, headers,
    )
    log(f"Meta title injecté — {handle_origin} | {meta_title!r}")

    # ── Étape 3 : meta description (global.description_tag) ──────────────────
    if generate_meta_desc and meta_description:
        set_product_metafield(
            product_id, "global", "description_tag",
            meta_description, "single_line_text_field",
            base_url, headers,
        )
        log(f"Meta description injectée — {handle_origin} | {meta_description[:60]!r}...")

    # ── Étape 4 : caractéristiques techniques (custom.caracteristique) ────────
    if caracteristique:
        set_product_metafield(
            product_id, "custom", "caracteristique",
            caracteristique, "multi_line_text_field",
            base_url, headers,
        )
        log(f"Caractéristiques injectées — {handle_origin}")
