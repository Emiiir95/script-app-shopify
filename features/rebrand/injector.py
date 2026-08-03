#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Rebrand : remplacement textuel sur les produits Shopify.

Champs traités par produit :
  - descriptionHtml  : description HTML (body_html)
  - seo.title        : meta title (global.title_tag)
  - seo.description  : meta description (global.description_tag)

Les remplacements sont définis dans config.json sous "rebrand.replacements" :
  [
    { "from": "le-perchoir-du-chat.com", "to": "perchoirduchat.com" },
    { "from": "Le Perchoir Du Chat",     "to": "Perchoir Du Chat"  }
  ]

Fonctions publiques :
  - fetch_all_products_seo  : récupère tous les produits avec SEO via GraphQL
  - apply_replacements      : applique les remplacements sur un texte
  - compute_product_changes : calcule les champs modifiés sans écrire
  - update_product          : écrit les changements sur Shopify
"""

import csv
import os
from datetime import datetime

from shopify.client import graphql_request
from utils.logger import log


# ── Fetch ──────────────────────────────────────────────────────────────────────

def fetch_all_products_seo(base_url, headers):
    """
    Récupère tous les produits avec description et SEO via GraphQL.

    Returns:
        list de dicts { gid, handle, title, description_html, seo_title, seo_description }
    """
    query = """
query($cursor: String) {
  products(first: 50, after: $cursor) {
    nodes {
      id
      handle
      title
      descriptionHtml
      seo { title description }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""
    products = []
    cursor   = None
    while True:
        data  = graphql_request(base_url, headers, query, {"cursor": cursor})
        page  = data.get("data", {}).get("products", {})
        for node in page.get("nodes", []):
            products.append({
                "gid":              node["id"],
                "handle":           node.get("handle", ""),
                "title":            node.get("title", ""),
                "description_html": node.get("descriptionHtml", "") or "",
                "seo_title":        node.get("seo", {}).get("title", "") or "",
                "seo_description":  node.get("seo", {}).get("description", "") or "",
            })
        page_info = page.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]

    log(f"Rebrand — {len(products)} produit(s) récupérés")
    return products


# ── Remplacements ──────────────────────────────────────────────────────────────

def apply_replacements(text, replacements):
    """
    Applique une liste de remplacements sur un texte.

    Args:
        text         : str
        replacements : list de dicts { "from": str, "to": str }

    Returns:
        str modifié
    """
    if not text:
        return text
    for r in replacements:
        old = r.get("from", "")
        new = r.get("to", "")
        if old:
            text = text.replace(old, new)
    return text


def compute_product_changes(product, replacements):
    """
    Calcule les champs à modifier sans rien écrire.

    Returns:
        dict { "changed": bool, "fields": { field: (old, new) } }
        Seuls les champs réellement modifiés apparaissent dans "fields".
    """
    fields = {}
    for field in ("description_html", "seo_title", "seo_description"):
        old = product.get(field, "") or ""
        new = apply_replacements(old, replacements)
        if new != old:
            fields[field] = (old, new)

    return {"changed": bool(fields), "fields": fields}


# ── Update ─────────────────────────────────────────────────────────────────────

_MUTATION_UPDATE = """
mutation productUpdate($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id handle }
    userErrors { field message }
  }
}"""


def update_product(product, changes, base_url, headers):
    """
    Écrit les champs modifiés sur Shopify via productUpdate.

    Args:
        product : dict issu de fetch_all_products_seo
        changes : dict issu de compute_product_changes
    """
    fields  = changes.get("fields", {})
    payload = {"id": product["gid"]}

    if "description_html" in fields:
        payload["descriptionHtml"] = fields["description_html"][1]

    if "seo_title" in fields or "seo_description" in fields:
        payload["seo"] = {}
        if "seo_title" in fields:
            payload["seo"]["title"] = fields["seo_title"][1]
        if "seo_description" in fields:
            payload["seo"]["description"] = fields["seo_description"][1]

    data   = graphql_request(base_url, headers, _MUTATION_UPDATE, {"input": payload})
    errors = data.get("data", {}).get("productUpdate", {}).get("userErrors", [])
    if errors:
        raise Exception(f"productUpdate — userErrors: {errors}")

    log(f"Rebrand OK — {product['handle']} | champs: {list(fields)}")


# ── Rapport CSV ────────────────────────────────────────────────────────────────

_FIELD_LABELS = {
    "description_html": "Description HTML",
    "seo_title":        "Meta Title",
    "seo_description":  "Meta Description",
}


def generate_report(report_rows, store_path):
    """
    Génère un rapport CSV des modifications effectuées.

    Returns:
        str : chemin absolu du fichier CSV
    """
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", f"rebrand_rapport_{timestamp}.csv")
    fieldnames = ["handle", "titre", "champ", "statut", "erreur"]

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in report_rows:
            writer.writerow(row)

    log(f"Rapport rebrand généré : {csv_path}")
    print(f"\n[RAPPORT] CSV : {csv_path}")
    return csv_path
