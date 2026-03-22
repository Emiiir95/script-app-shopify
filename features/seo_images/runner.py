#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration SEO Images.

Flow :
  1. Récupère tous les produits avec leurs images et meta title (GraphQL)
  2. Résumé terminal + confirmation utilisateur
  3. Construit la liste des mises à jour (filename slug + alt text)
  4. Lance fileUpdate par batch via injector
  5. Rapport CSV post-injection horodaté

Règles appliquées (identiques à Crush: Speed & Image Optimizer) :
  - filename  = {meta_title_slug}-{position}.{ext}
  - alt text  = meta title (ou titre produit si meta title absent)
  - L'URL CDN change mais les thèmes Liquid s'auto-mettent à jour
    car ils utilisent {{ product.images }} dynamiquement.
"""

import sys

from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, graphql_request, SHOPIFY_API_VERSION
from features.seo_images.injector import (
    slugify_title,
    _get_extension,
    update_images_seo,
    generate_injection_report,
)
from utils.logger import log, LOG_FILE


def _fetch_products_with_seo_images(base_url, headers):
    """
    Récupère tous les produits avec leurs images MediaImage GIDs et meta title
    via une seule requête GraphQL paginée.

    Returns:
        list de dicts {
            "handle"     : str,
            "meta_title" : str,   # global.title_tag ou title si absent
            "images"     : [{"gid": str, "url": str}, ...]
        }
    """
    query = """
    query getProductsSEOImages($cursor: String) {
      products(first: 50, after: $cursor) {
        edges {
          cursor
          node {
            handle
            title
            metafield(namespace: "global", key: "title_tag") {
              value
            }
            media(first: 20) {
              edges {
                node {
                  ... on MediaImage {
                    id
                    image { url }
                  }
                }
              }
            }
          }
        }
        pageInfo { hasNextPage }
      }
    }
    """

    products = []
    cursor   = None

    while True:
        variables = {"cursor": cursor} if cursor else {}
        data      = graphql_request(base_url, headers, query, variables)
        edges     = data["data"]["products"].get("edges", [])
        page_info = data["data"]["products"].get("pageInfo", {})

        for edge in edges:
            node       = edge["node"]
            handle     = node["handle"]
            title      = node.get("title", "")
            meta_title = (node.get("metafield") or {}).get("value") or title
            cursor     = edge.get("cursor")

            images = []
            for m in node.get("media", {}).get("edges", []):
                media_node = m["node"]
                gid = media_node.get("id")
                url = (media_node.get("image") or {}).get("url", "")
                if gid:
                    images.append({"gid": gid, "url": url})

            products.append({
                "handle":     handle,
                "meta_title": meta_title,
                "images":     images,
            })

        if not page_info.get("hasNextPage"):
            break

    log(f"SEO Images — {len(products)} produit(s) récupéré(s) via GraphQL")
    return products


def _build_image_updates(products):
    """
    Construit la liste complète des mises à jour d'images.

    Returns:
        list de dicts {gid, filename, alt, handle, position}
    """
    updates = []
    for product in products:
        handle     = product["handle"]
        meta_title = product["meta_title"]
        slug       = slugify_title(meta_title)
        alt        = meta_title

        for pos, img in enumerate(product["images"], start=1):
            ext      = _get_extension(img["url"])
            filename = f"{slug}-{pos}{ext}"
            updates.append({
                "gid":      img["gid"],
                "filename": filename,
                "alt":      alt,
                "handle":   handle,
                "position": pos,
            })

    return updates


def run(store_config, store_path):
    """
    Point d'entrée de la feature SEO Images.

    Args:
        store_config : dict { name, store_url, access_token }
        store_path   : chemin absolu vers stores/{boutique}/
    """
    store_name = store_config.get("name", "boutique")

    log("=" * 60)
    log(f"Démarrage feature SEO Images — boutique : {store_name}")
    print("=" * 60)
    print(f"  SEO Images — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(store_config["access_token"])

    # ── Fetch produits + images ────────────────────────────────────────────────
    print("\n[1/3] Récupération des produits et images...")
    products = _fetch_products_with_seo_images(base_url, headers)

    if not products:
        log("Aucun produit trouvé — arrêt.", "error", also_print=True)
        sys.exit(1)

    image_updates = _build_image_updates(products)
    total_images  = len(image_updates)
    total_products_with_images = sum(1 for p in products if p["images"])

    # ── Résumé + confirmation ──────────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("  ANALYSE — SEO Images")
    print("─" * 50)
    print(f"  Produits            : {len(products)}")
    print(f"  Produits avec images: {total_products_with_images}")
    print(f"  Images à traiter    : {total_images}")
    print("─" * 50)
    print("\n  Règles qui seront appliquées :")
    print("  • filename = {meta-title-slug}-{position}.{ext}")
    print("  • alt text = meta title (ou titre si absent)")
    print("  • L'URL CDN va changer — les thèmes Liquid s'auto-mettent à jour")
    print("─" * 50)

    print("\n" + "=" * 60)
    answer = input("Lancer le renommage SEO des images ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("SEO Images annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    # ── Injection ──────────────────────────────────────────────────────────────
    print("\n[2/3] Mise à jour SEO des images en cours...")
    log("Début SEO Images — fileUpdate GraphQL")

    results = update_images_seo(image_updates, base_url, headers)

    ok_count  = sum(1 for r in results if r["statut"] == "OK")
    err_count = sum(1 for r in results if r["statut"] == "ERREUR")

    # ── Rapport ────────────────────────────────────────────────────────────────
    print("\n[3/3] Génération du rapport...")
    if results:
        generate_injection_report(results, store_path)

    # ── Résumé final ───────────────────────────────────────────────────────────
    log(f"Terminé SEO Images | OK: {ok_count} | Erreurs: {err_count}")
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique      : {store_name}")
    print(f"  Images OK     : {ok_count}")
    print(f"  Images KO     : {err_count}")
    print(f"  Logs          : {LOG_FILE}")
    print("=" * 60)
