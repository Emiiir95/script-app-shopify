#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Feature Balises : lecture live des collections + synchronisation des tags.

Les collections de la boutique sont des SMART COLLECTIONS construites sur la règle
« tag equals {condition} » (voir features/collections/injector.py). Un produit entre
donc dans une collection dès qu'il porte l'un de ses tags de condition.

Cette feature, en mode REMISE À PLAT (reset total) :
  - EFFACE tous les tags existants du produit,
  - remet UNIQUEMENT les tags des collections choisies par l'IA.
  → À la fin, le produit n'a QUE ce que le classement a décidé (les tags SEO/promo/
    manuels sont aussi supprimés — choix assumé).

⚠️ Tout est récupéré EN DIRECT depuis Shopify (produits ET collections) : on ne se fie
jamais à la config locale de l'app, qui peut être périmée.

Fonctions publiques :
  - fetch_collections_with_rules(base_url, headers) : collections réelles + conditions tag
  - normalize_tag(t)                                : normalise un tag (accents/casse/tirets)
  - compute_synced_tags(current, collections, chosen_handles) : nouveau champ tags (sync)
  - update_product_tags(product_id, tags, base_url, headers)  : PUT du champ tags
  - generate_injection_report(log, store_path)      : CSV post-injection horodaté
"""

import csv
import os
import re
import unicodedata
from datetime import datetime

from shopify.client import shopify_get, shopify_get_paginated, shopify_put
from utils.logger import log


def fetch_products_live(base_url, headers, status=None):
    """
    Récupère EN DIRECT tous les produits avec le contenu utile au classement
    (titre, description, type, tags actuels) — jamais depuis la config locale.

    Returns:
        list de dicts Shopify (id, handle, title, body_html, product_type, tags, status)
    """
    products = []
    url    = f"{base_url}/products.json"
    params = {"limit": 250, "fields": "id,handle,title,body_html,product_type,tags,status"}
    if status:
        params["status"] = status

    while url:
        data, link_header = shopify_get_paginated(url, headers, params=params)
        products.extend(data.get("products", []))
        url, params = None, None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    log(f"Balises — {len(products)} produit(s) récupéré(s) en direct")
    return products


# ── Normalisation ───────────────────────────────────────────────────────────────

def normalize_tag(t):
    """lowercase + sans accents + tirets → espaces, pour comparer des tags."""
    if not t:
        return ""
    n = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode("ascii").lower()
    n = re.sub(r"[-–]", " ", n)
    return re.sub(r"\s+", " ", n).strip()


def _tags_to_list(tags):
    """Champ tags Shopify (CSV str ou list) → liste de chaînes nettoyées."""
    if not tags:
        return []
    raw = tags.split(",") if isinstance(tags, str) else list(tags)
    return [t.strip() for t in raw if t and t.strip()]


# ── Lecture live des collections + leurs règles de tag ──────────────────────────

def fetch_collections_with_rules(base_url, headers):
    """
    Récupère EN DIRECT toutes les smart collections avec leurs conditions de tag.

    Returns:
        list de dicts {
            "handle", "title", "description",
            "conditions": [str, ...],   # tags qui font entrer un produit (rule column=tag)
        }
        (les collections sans condition de tag sont incluses mais avec conditions=[]
         → l'IA peut toujours les proposer, mais on ne peut pas les tagger.)
    """
    collections = []
    url    = f"{base_url}/smart_collections.json"
    params = {"limit": 250, "fields": "id,handle,title,body_html,rules"}

    while url:
        data  = shopify_get(url, headers, params=params)
        batch = data.get("smart_collections", [])
        for col in batch:
            conditions = [
                r.get("condition", "").strip()
                for r in col.get("rules", [])
                if r.get("column") == "tag" and r.get("relation") == "equals" and r.get("condition")
            ]
            collections.append({
                "handle":      col.get("handle", ""),
                "title":       col.get("title", ""),
                "description": col.get("body_html", "") or "",
                "conditions":  conditions,
            })
        if len(batch) < 250:
            break
        params = {"limit": 250, "fields": "id,handle,title,body_html,rules",
                  "since_id": batch[-1]["id"]}

    log(f"Balises — {len(collections)} collection(s) récupérée(s) en direct")
    return collections


def _primary_condition(col):
    """Tag à ajouter pour faire entrer un produit : celui égal au nom si présent, sinon le 1er."""
    conds = col.get("conditions") or []
    if not conds:
        return None
    title_norm = normalize_tag(col.get("title", ""))
    for c in conds:
        if normalize_tag(c) == title_norm:
            return c
    return conds[0]


# ── Cœur : synchronisation des tags d'un produit ────────────────────────────────

def compute_synced_tags(current_tags, collections, chosen_handles):
    """
    Calcule le NOUVEAU champ tags d'un produit en mode REMISE À PLAT (reset total).

    On EFFACE tous les tags existants du produit et on garde UNIQUEMENT les tags des
    collections choisies par l'IA. À la fin, le produit n'a QUE ce que le classement a
    décidé — les tags SEO/promo/manuels sont AUSSI supprimés (choix assumé : « il doit
    n'y avoir que ce que le bot a fait »).

    Args:
        current_tags   : champ tags actuel (CSV str ou list)
        collections    : list de dicts {handle, title, conditions:[...]} (live Shopify)
        chosen_handles : handles des collections où le produit doit être (IA)

    Returns:
        dict { "new_tags": [...], "added": [...], "removed": [...], "changed": bool }
    """
    col_by_handle = {c.get("handle"): c for c in collections}

    # Nouveaux tags = UNIQUEMENT les tags des collections choisies (ordre IA, dédoublonné).
    new_tags, seen = [], set()
    for h in (chosen_handles or []):
        col = col_by_handle.get(h)
        if not col:
            continue
        primary = _primary_condition(col)
        if not primary:
            continue                     # collection sans règle de tag → intaggable
        n = normalize_tag(primary)
        if n and n not in seen:
            seen.add(n)
            new_tags.append(primary)

    current_list  = _tags_to_list(current_tags)
    current_norms = {normalize_tag(t) for t in current_list}

    added = [t for t in new_tags if normalize_tag(t) not in current_norms]

    removed, rseen = [], set()
    for t in current_list:              # tout tag qui ne fait pas partie des nouveaux → retiré
        n = normalize_tag(t)
        if n in seen or n in rseen:
            continue
        rseen.add(n)
        removed.append(t)

    return {
        "new_tags": new_tags,
        "added":    added,
        "removed":  removed,
        "changed":  seen != current_norms,
    }


# ── Écriture Shopify ─────────────────────────────────────────────────────────────

def update_product_tags(product_id, new_tags, base_url, headers):
    """Met à jour le champ tags d'un produit (REST PUT). new_tags = liste → CSV."""
    tags_csv = ", ".join(new_tags)
    shopify_put(
        f"{base_url}/products/{product_id}.json",
        headers,
        {"product": {"id": product_id, "tags": tags_csv}},
    )
    return tags_csv


# ── Rapport ──────────────────────────────────────────────────────────────────────

def generate_injection_report(injection_log, store_path):
    """CSV horodaté : date, handle, tags_ajoutes, tags_retires, collections, statut, erreur."""
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path = os.path.join(store_path, "rapports", f"balises_rapport_{timestamp}.csv")
    fieldnames = ["date_heure", "handle", "tags_ajoutes", "tags_retires",
                  "collections", "statut", "erreur"]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for e in injection_log:
            writer.writerow({
                "date_heure":   now_str,
                "handle":       e.get("handle", ""),
                "tags_ajoutes": ", ".join(e.get("added", [])),
                "tags_retires": ", ".join(e.get("removed", [])),
                "collections":  ", ".join(e.get("collections", [])),
                "statut":       e.get("statut", ""),
                "erreur":       e.get("erreur", ""),
            })

    log(f"Rapport Balises généré : {csv_path}")
    print(f"\n[RAPPORT] CSV : {csv_path}")
    return csv_path
