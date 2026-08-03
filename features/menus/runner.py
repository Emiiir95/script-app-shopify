#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration de la feature Menus.

Flow :
  1. Lit la config "menus" depuis store_config (config.json)
  2. Charge les maps handles→GIDs (collections, pages, blogs)
  3. Affiche un résumé des menus à créer/mettre à jour
  4. Demande confirmation
  5. Upsert chaque menu (delete + create si existe déjà)
  6. Affiche le résumé final

Scope token requis : write_online_store_navigation
"""

import sys

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from features.menus.injector import (
    upsert_menu,
    _fetch_collection_gids,
    _fetch_page_gids,
    _fetch_blog_gids,
    _fetch_policy_gids,
    fetch_menu_gid,
)
from utils.logger import log, LOG_FILE


def _print_item_tree(items, indent=4):
    """Affiche les items du menu en arborescence."""
    for item in items:
        item_type = item.get("type", "")
        handle    = item.get("handle", item.get("url", ""))
        prefix    = " " * indent + "• "
        suffix    = f"  [{item_type}]" + (f" → {handle}" if handle else "")
        print(f"{prefix}{item.get('title', '')}{suffix}")
        if item.get("items"):
            _print_item_tree(item["items"], indent + 4)


def run(store_config, store_path):
    """
    Point d'entrée de la feature Menus.

    Args:
        store_config : dict { name, store_url, access_token, ... }
        store_path   : chemin absolu vers stores/{boutique}/
    """
    store_name  = store_config.get("name", "boutique")
    menus_cfg   = store_config.get("menus", [])

    log("=" * 60)
    log(f"Démarrage feature Menus — boutique : {store_name}")
    print("=" * 60)
    print(f"  Menus de navigation — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    if not menus_cfg:
        print("\n[INFO] Aucun menu défini dans config.json.")
        print('  → Ajoutez une clé "menus" dans votre config.json')
        print("  → Voir le template stores/_template/config.json pour la structure")
        return

    base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(store_config["access_token"])

    # ── Résolution des handles ────────────────────────────────────────────────
    print("\n[1/3] Chargement des ressources Shopify...")
    print("  → Collections...", end=" ", flush=True)
    collection_map = _fetch_collection_gids(base_url, headers)
    print(f"{len(collection_map)} trouvée(s)")

    print("  → Pages...", end=" ", flush=True)
    page_map = _fetch_page_gids(base_url, headers)
    print(f"{len(page_map)} trouvée(s)")

    print("  → Blogs...", end=" ", flush=True)
    blog_map = _fetch_blog_gids(base_url, headers)
    print(f"{len(blog_map)} trouvé(s)")

    print("  → Politiques Shopify...", end=" ", flush=True)
    policy_map = _fetch_policy_gids(base_url, headers)
    print(f"{len(policy_map)} trouvée(s)")

    # ── Résumé avant confirmation ─────────────────────────────────────────────
    print(f"\n[2/3] {len(menus_cfg)} menu(s) à traiter :\n")
    for menu_cfg in menus_cfg:
        handle     = menu_cfg.get("handle", "")
        title      = menu_cfg.get("title", "")
        items      = menu_cfg.get("items", [])
        existing   = fetch_menu_gid(handle, base_url, headers)
        action_lbl = "MISE À JOUR" if existing else "CRÉATION"
        print(f"  [{action_lbl}] {title!r}  (handle: {handle})  — {len(items)} item(s) racine")
        _print_item_tree(items)
        print()

    answer = input("Lancer l'injection des menus ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Menus — annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    # ── Injection ─────────────────────────────────────────────────────────────
    print("\n[3/3] Injection en cours...\n")
    ok_count  = 0
    err_count = 0

    for menu_cfg in menus_cfg:
        handle = menu_cfg.get("handle", "")
        title  = menu_cfg.get("title", "")
        print(f"  → {title!r} ({handle})...", end=" ", flush=True)

        result = upsert_menu(menu_cfg, collection_map, page_map, blog_map, policy_map, base_url, headers)

        if result["statut"] == "ERREUR":
            err_count += 1
            print(f"[ERREUR] {result['erreur']}")
        else:
            ok_count += 1
            print(f"[{result['statut']}] — {result['items_count']} item(s)")

    # ── Résumé final ──────────────────────────────────────────────────────────
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique   : {store_name}")
    print(f"  Menus OK   : {ok_count}")
    print(f"  Erreurs    : {err_count}")
    print(f"  Logs       : {LOG_FILE}")
    print("=" * 60)
    log(f"Terminé Menus | OK: {ok_count} | Erreurs: {err_count}")
