#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Création et mise à jour des menus de navigation Shopify.

Flow par menu :
  1. Résolution des handles (collections, pages, politiques) en GIDs via GraphQL
  2. Vérification si le menu existe déjà (par handle) via listing
  3. Si existant  → menuDelete puis menuCreate
  4. Si inexistant → menuCreate

Types supportés dans la config :
  FRONTPAGE    — page d'accueil (pas de resourceId)
  CATALOG      — toute la boutique (pas de resourceId)
  COLLECTION   — collection spécifique       (champ "handle" requis)
  PAGE         — page personnalisée          (champ "handle" requis)
  HTTP         — URL externe/interne         (champ "url" requis)
  BLOG         — blog                        (champ "handle" requis)
  SHOP_POLICY  — politique Shopify intégrée  (champ "policy_type" requis)
                 Valeurs policy_type : REFUND_POLICY, PRIVACY_POLICY,
                 TERMS_OF_SERVICE, SHIPPING_POLICY, CONTACT_INFORMATION,
                 TERMS_OF_SALE, LEGAL_NOTICE

Scope token requis : read_online_store_navigation, write_online_store_navigation
"""

from shopify.client import graphql_request
from utils.logger import log


# ── Résolution handles → GIDs ──────────────────────────────────────────────────

def _fetch_collection_gids(base_url, headers):
    """Retourne { handle: gid } pour toutes les collections."""
    query = """
query($cursor: String) {
  collections(first: 250, after: $cursor) {
    nodes { id handle }
    pageInfo { hasNextPage endCursor }
  }
}"""
    result = {}
    cursor = None
    while True:
        data  = graphql_request(base_url, headers, query, {"cursor": cursor})
        cols  = data.get("data", {}).get("collections", {})
        for node in cols.get("nodes", []):
            result[node["handle"]] = node["id"]
        page_info = cols.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]
    return result


def _fetch_page_gids(base_url, headers):
    """Retourne { handle: gid } pour toutes les pages."""
    query = """
query($cursor: String) {
  pages(first: 250, after: $cursor) {
    nodes { id handle }
    pageInfo { hasNextPage endCursor }
  }
}"""
    result = {}
    cursor = None
    while True:
        data  = graphql_request(base_url, headers, query, {"cursor": cursor})
        pages = data.get("data", {}).get("pages", {})
        for node in pages.get("nodes", []):
            result[node["handle"]] = node["id"]
        page_info = pages.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]
    return result


def _fetch_blog_gids(base_url, headers):
    """Retourne { handle: gid } pour tous les blogs."""
    query = """
query($cursor: String) {
  blogs(first: 50, after: $cursor) {
    nodes { id handle }
    pageInfo { hasNextPage endCursor }
  }
}"""
    result = {}
    cursor = None
    while True:
        data  = graphql_request(base_url, headers, query, {"cursor": cursor})
        blogs = data.get("data", {}).get("blogs", {})
        for node in blogs.get("nodes", []):
            result[node["handle"]] = node["id"]
        page_info = blogs.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]
    return result


def _fetch_policy_gids(base_url, headers):
    """
    Retourne { policy_type: gid } pour toutes les politiques Shopify.
    Ex: { "REFUND_POLICY": "gid://shopify/ShopPolicy/123", ... }
    """
    query = """
query {
  shop {
    shopPolicies {
      type
      id
    }
  }
}"""
    try:
        data     = graphql_request(base_url, headers, query, {})
        policies = data.get("data", {}).get("shop", {}).get("shopPolicies", [])
        return {p["type"]: p["id"] for p in policies}
    except Exception as e:
        log(f"Impossible de récupérer les politiques Shopify : {e}", "warning")
        return {}


# ── Recherche menu existant ────────────────────────────────────────────────────

def fetch_menu_gid(handle, base_url, headers):
    """
    Retourne le GID du menu correspondant au handle, ou None s'il n'existe pas.
    L'API ne supporte pas le filtre par handle — on liste tous les menus.
    """
    query = """
query($cursor: String) {
  menus(first: 50, after: $cursor) {
    nodes { id handle title }
    pageInfo { hasNextPage endCursor }
  }
}"""
    cursor = None
    while True:
        data  = graphql_request(base_url, headers, query, {"cursor": cursor})
        menus = data.get("data", {}).get("menus", {})
        for node in menus.get("nodes", []):
            if node.get("handle") == handle:
                return node["id"]
        page_info = menus.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]
    return None


# ── Construction des items ─────────────────────────────────────────────────────

def _build_items(items_cfg, collection_map, page_map, blog_map, policy_map, depth=0):
    """
    Convertit la config JSON en liste MenuItemCreateInput.

    Args:
        items_cfg   : liste de dicts depuis config.json
        collection_map : { handle: gid }
        page_map       : { handle: gid }
        blog_map       : { handle: gid }
        policy_map     : { policy_type: gid }
        depth          : niveau d'imbrication (max 3)

    Returns:
        list de dicts compatibles MenuItemCreateInput
    """
    if depth >= 3:
        return []

    result = []
    for item in items_cfg:
        item_type = item.get("type", "").upper()
        title     = item.get("title", "")
        sub_items = item.get("items", [])

        built = {"title": title, "type": item_type}

        if item_type in ("FRONTPAGE", "CATALOG"):
            pass

        elif item_type == "COLLECTION":
            handle = item.get("handle", "")
            gid    = collection_map.get(handle)
            if not gid:
                log(f"Menu — collection introuvable : handle={handle!r}", "warning", also_print=True)
                continue
            built["resourceId"] = gid

        elif item_type == "PAGE":
            handle = item.get("handle", "")
            gid    = page_map.get(handle)
            if not gid:
                log(f"Menu — page introuvable : handle={handle!r}", "warning", also_print=True)
                continue
            built["resourceId"] = gid

        elif item_type == "BLOG":
            handle = item.get("handle", "")
            gid    = blog_map.get(handle)
            if not gid:
                log(f"Menu — blog introuvable : handle={handle!r}", "warning", also_print=True)
                continue
            built["resourceId"] = gid

        elif item_type == "SHOP_POLICY":
            policy_type = item.get("policy_type", "")
            gid         = policy_map.get(policy_type)
            if not gid:
                log(f"Menu — politique introuvable : {policy_type!r} (politique non créée ?)", "warning", also_print=True)
                continue
            built["resourceId"] = gid

        elif item_type == "HTTP":
            url = item.get("url", "")
            if not url:
                log(f"Menu — item HTTP sans url : {title!r}", "warning", also_print=True)
                continue
            built["url"] = url

        else:
            log(f"Menu — type inconnu ignoré : {item_type!r} ({title!r})", "warning", also_print=True)
            continue

        if sub_items and depth < 2:
            nested = _build_items(sub_items, collection_map, page_map, blog_map, policy_map, depth + 1)
            if nested:
                built["items"] = nested

        result.append(built)

    return result


# ── Mutations GraphQL ──────────────────────────────────────────────────────────

_MUTATION_CREATE = """
mutation menuCreate($title: String!, $handle: String!, $items: [MenuItemCreateInput!]!) {
  menuCreate(title: $title, handle: $handle, items: $items) {
    menu { id handle title }
    userErrors { field message }
  }
}"""

_MUTATION_UPDATE = """
mutation menuUpdate($id: ID!, $title: String!, $items: [MenuItemUpdateInput!]!) {
  menuUpdate(id: $id, title: $title, items: $items) {
    menu { id handle title }
    userErrors { field message }
  }
}"""

_MUTATION_DELETE = """
mutation menuDelete($id: ID!) {
  menuDelete(id: $id) {
    deletedMenuId
    userErrors { field message }
  }
}"""


def _delete_menu(menu_id, base_url, headers):
    data   = graphql_request(base_url, headers, _MUTATION_DELETE, {"id": menu_id})
    errors = data.get("data", {}).get("menuDelete", {}).get("userErrors", [])
    if errors:
        raise Exception(f"menuDelete — userErrors: {errors}")
    log(f"Menu supprimé : {menu_id}")


def _create_menu(title, handle, items, base_url, headers):
    variables = {"title": title, "handle": handle, "items": items}
    data      = graphql_request(base_url, headers, _MUTATION_CREATE, variables)
    payload   = data.get("data", {}).get("menuCreate", {})
    errors    = payload.get("userErrors", [])
    if errors:
        raise Exception(f"menuCreate — userErrors: {errors}")
    menu = payload.get("menu", {})
    log(f"Menu créé : {handle!r} | GID: {menu.get('id')}")
    return menu


def _update_menu(menu_id, title, new_items, base_url, headers):
    """
    Met à jour un menu existant (y compris les menus par défaut non supprimables).
    menuUpdate remplace directement l'intégralité des items — pas de delete/create wrappers.
    """
    variables = {"id": menu_id, "title": title, "items": new_items}
    data      = graphql_request(base_url, headers, _MUTATION_UPDATE, variables)
    payload   = data.get("data", {}).get("menuUpdate", {})
    errors    = payload.get("userErrors", [])
    if errors:
        raise Exception(f"menuUpdate — userErrors: {errors}")
    menu = payload.get("menu", {})
    log(f"Menu mis à jour : {menu.get('handle')!r} | GID: {menu.get('id')}")
    return menu


# ── Fonction publique principale ───────────────────────────────────────────────

def upsert_menu(menu_cfg, collection_map, page_map, blog_map, policy_map, base_url, headers):
    """
    Crée ou met à jour un menu Shopify à partir de sa configuration.

    Pour les menus existants (y compris les menus par défaut non supprimables),
    utilise menuUpdate avec suppression complète des items + recréation.

    Args:
        menu_cfg       : dict { title, handle, items: [...] }
        collection_map : { handle: gid }
        page_map       : { handle: gid }
        blog_map       : { handle: gid }
        policy_map     : { policy_type: gid }
        base_url       : URL de base REST
        headers        : dict headers Shopify

    Returns:
        dict { handle, title, statut, items_count, erreur }
    """
    title  = menu_cfg.get("title", "")
    handle = menu_cfg.get("handle", "")

    try:
        items = _build_items(
            menu_cfg.get("items", []),
            collection_map, page_map, blog_map, policy_map
        )
        if not items:
            raise Exception("Aucun item valide — vérifier les handles/policy_type dans la config")

        existing_id = fetch_menu_gid(handle, base_url, headers)
        if existing_id:
            _update_menu(existing_id, title, items, base_url, headers)
            action = "MIS À JOUR"
        else:
            _create_menu(title, handle, items, base_url, headers)
            action = "CRÉÉ"

        return {
            "handle":      handle,
            "title":       title,
            "statut":      action,
            "items_count": len(items),
            "erreur":      "",
        }

    except Exception as e:
        log(f"Erreur menu {handle!r} : {e}", "error", also_print=True)
        return {
            "handle":      handle,
            "title":       title,
            "statut":      "ERREUR",
            "items_count": 0,
            "erreur":      str(e),
        }
