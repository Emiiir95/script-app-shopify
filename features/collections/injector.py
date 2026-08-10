#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Création/mise à jour des collections Shopify.

Utilise l'API REST Smart Collections (collections automatiques par règle tag).

Fonctions publiques :
  - fetch_existing_collections  : récupère toutes les smart collections existantes
  - get_handle_from_url         : extrait le handle depuis l'URL de collection
  - find_collection_by_handle   : cherche une collection dans la liste existante
  - create_collection           : crée une nouvelle smart collection avec règle tag
  - update_collection           : met à jour description + SEO d'une collection existante
  - generate_injection_report   : CSV post-injection horodaté
"""

import csv
import os
from datetime import datetime

from shopify.client import shopify_get, shopify_post, shopify_put
from utils.logger import log


def fetch_existing_collections(base_url, headers):
    """
    Récupère toutes les smart collections existantes (paginées).

    Returns:
        list de dicts Shopify smart_collection
    """
    collections = []
    url    = f"{base_url}/smart_collections.json"
    params = {"limit": 250, "fields": "id,handle,title"}

    while url:
        data        = shopify_get(url, headers, params=params)
        batch       = data.get("smart_collections", [])
        collections.extend(batch)

        # Pagination via Link header non disponible dans shopify_get simple
        # On itère tant qu'on reçoit 250 (limite max)
        if len(batch) < 250:
            break
        # Page suivante via since_id
        params = {"limit": 250, "fields": "id,handle,title", "since_id": batch[-1]["id"]}

    log(f"Collections — {len(collections)} smart collection(s) existante(s)")
    return collections


def get_handle_from_url(url):
    """
    Extrait le handle depuis l'URL de collection.
    Ex: "https://le-perchoir-du-chat.com/collections/arbre-a-chat-xxl" → "arbre-a-chat-xxl"
    """
    return url.rstrip("/").split("/")[-1]


def find_collection_by_handle(handle, existing_collections):
    """
    Cherche une collection par son handle dans la liste existante.

    Returns:
        dict ou None
    """
    for col in existing_collections:
        if col.get("handle") == handle:
            return col
    return None


def _set_collection_metafield(collection_id, namespace, key, value, value_type, base_url, headers):
    """
    Crée ou met à jour un metafield sur une collection via l'endpoint REST.
    Même logique que set_product_metafield mais pour les collections.
    """
    mf_url   = f"{base_url}/collections/{collection_id}/metafields.json"
    existing = shopify_get(mf_url, headers)
    mf_id    = None
    for mf in existing.get("metafields", []):
        if mf.get("namespace") == namespace and mf.get("key") == key:
            mf_id = mf["id"]
            break

    payload = {
        "metafield": {
            "namespace": namespace,
            "key":       key,
            "value":     value,
            "type":      value_type,
        }
    }

    if mf_id:
        shopify_put(f"{base_url}/metafields/{mf_id}.json", headers, payload)
    else:
        shopify_post(f"{base_url}/collections/{collection_id}/metafields.json", headers, payload)


def _http_error_detail(exc):
    """
    Extrait le corps de réponse d'une HTTPError Shopify (les 422 y détaillent
    la vraie cause, ex: {"errors": {"handle": ["has already been taken"]}}).
    Retourne une chaîne courte ou "" si indisponible.
    """
    resp = getattr(exc, "response", None)
    if resp is None:
        return ""
    try:
        body = resp.json()
        errors = body.get("errors", body)
        return str(errors)
    except Exception:
        return (getattr(resp, "text", "") or "").strip()[:300]


def _is_handle_taken(detail):
    """True si le détail d'erreur indique un handle déjà pris (collection fantôme)."""
    d = (detail or "").lower()
    return "handle" in d and ("already been taken" in d or "already taken" in d or "déjà" in d)


def build_tag_rules(name, tags=None):
    """
    Construit les règles d'inclusion « tag equals » d'une smart collection.

    Toujours : le NOM de la collection comme tag (un produit taggé avec le nom
    de la collection y entre). Plus, en OR, les tags de config s'il y en a.
    Déduplication insensible à la casse.

    Returns:
        list de règles Shopify [{column: "tag", relation: "equals", condition: ...}]
    """
    conditions = []
    seen = set()
    for c in [name] + list(tags or []):
        c = (c or "").strip()
        if c and c.lower() not in seen:
            seen.add(c.lower())
            conditions.append(c)
    return [{"column": "tag", "relation": "equals", "condition": c} for c in conditions]


def create_collection(collection_config, description, meta_title, meta_desc, base_url, headers):
    """
    Crée une nouvelle smart collection avec règle tag automatique,
    puis injecte meta title et meta description via metafields.

    Args:
        collection_config : dict { name, tags, url, volume }
        description       : HTML body_html
        meta_title        : meta title SEO
        meta_desc         : meta description SEO
        base_url          : URL de base REST Shopify
        headers           : dict headers Shopify

    Returns:
        dict : smart_collection créée ou None si erreur
    """
    handle = get_handle_from_url(collection_config["url"])
    rules  = build_tag_rules(collection_config["name"], collection_config.get("tags", []))

    payload = {
        "smart_collection": {
            "title":       collection_config["name"],
            "handle":      handle,
            "body_html":   description,
            "rules":       rules,
            "disjunctive": True,
            "published":   True,
        }
    }

    try:
        data       = shopify_post(f"{base_url}/smart_collections.json", headers, payload)
        result     = data.get("smart_collection", {})
        col_id     = result.get("id")
        log(f"Collection CRÉÉE : {collection_config['name']} (id: {col_id})")

        if col_id:
            if meta_title:
                _set_collection_metafield(col_id, "global", "title_tag", meta_title, "single_line_text_field", base_url, headers)
            if meta_desc:
                _set_collection_metafield(col_id, "global", "description_tag", meta_desc, "single_line_text_field", base_url, headers)

        return result
    except Exception as e:
        detail = _http_error_detail(e)
        if _is_handle_taken(detail):
            log(f"Collection IGNORÉE '{collection_config['name']}' : le handle '{handle}' est déjà "
                f"réservé côté Shopify (collection fantôme/introuvable via l'API). "
                f"→ Recréez ou renommez cette collection dans l'admin Shopify, puis relancez.",
                "warning", also_print=True)
        else:
            suffix = f" — {detail}" if detail else ""
            log(f"Erreur création collection '{collection_config['name']}' : {e}{suffix}", "error", also_print=True)
        return None


def update_collection(collection_id, collection_name, description, meta_title, meta_desc, base_url, headers, tags=None):
    """
    Met à jour description + règles tag + meta SEO d'une collection existante.
    Meta title et meta description injectés via metafields (namespace global).

    Args:
        collection_id   : id Shopify de la smart collection
        collection_name : nom de la collection (aussi utilisé comme tag de règle)
        description     : HTML body_html
        meta_title      : meta title SEO
        meta_desc       : meta description SEO
        base_url        : URL de base REST Shopify
        headers         : dict headers Shopify
        tags            : tags de config (en plus du nom) — optionnel

    Returns:
        dict : smart_collection mise à jour ou None si erreur
    """
    payload = {
        "smart_collection": {
            "id":          collection_id,
            "body_html":   description,
            "rules":       build_tag_rules(collection_name, tags),
            "disjunctive": True,
        }
    }

    try:
        data   = shopify_put(f"{base_url}/smart_collections/{collection_id}.json", headers, payload)
        result = data.get("smart_collection", {})
        log(f"Collection MISE À JOUR : {collection_name} (id: {collection_id})")

        if meta_title:
            _set_collection_metafield(collection_id, "global", "title_tag", meta_title, "single_line_text_field", base_url, headers)
        if meta_desc:
            _set_collection_metafield(collection_id, "global", "description_tag", meta_desc, "single_line_text_field", base_url, headers)

        return result
    except Exception as e:
        detail = _http_error_detail(e)
        suffix = f" — {detail}" if detail else ""
        log(f"Erreur update collection '{collection_name}' : {e}{suffix}", "error", also_print=True)
        return None


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-injection des collections.

    Colonnes :
        date_heure, nom, handle, action (CRÉÉE/MISE À JOUR/ERREUR),
        meta_title, meta_desc_apercu, statut, erreur

    Returns:
        str : chemin absolu du rapport
    """
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", f"collections_rapport_{timestamp}.csv")
    fieldnames = [
        "date_heure", "nom", "handle", "action",
        "meta_title", "meta_desc_apercu", "statut", "erreur",
    ]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            writer.writerow({
                "date_heure":      now_str,
                "nom":             entry.get("nom", ""),
                "handle":          entry.get("handle", ""),
                "action":          entry.get("action", ""),
                "meta_title":      entry.get("meta_title", ""),
                "meta_desc_apercu": entry.get("meta_desc", "")[:80],
                "statut":          entry.get("statut", ""),
                "erreur":          entry.get("erreur", ""),
            })

    log(f"Rapport collections généré : {csv_path}")
    print(f"\n[RAPPORT] CSV : {csv_path}")
    return csv_path
