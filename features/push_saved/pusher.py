#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
pusher.py — Repousse la data DÉJÀ GÉNÉRÉE (payée) vers Shopify, SANS OpenAI.

Lit les CSV d'aperçu (rapports/*_preview.csv, écrits avant injection) et ré-injecte
via les injecteurs existants. Utile quand des produits ont été sautés (features
lancées en parallèle) : on pousse ce qui a déjà été généré sans re-générer.

- SEO Boost : seo_boost_preview.csv → title/handle/body_html + meta title/desc.
              (les « caractéristiques » ne sont PAS dans le CSV → non restaurées)
- Reviews   : reviews_preview.csv → metaobjects avis_client + note globale
              (ne remplit que les slots avis_client vides → pas de doublon).

Matching produit par handle. Comme SEO Boost change les handles, on essaie le
handle d'origine ET le nouveau (via l'alias construit depuis le CSV SEO).
"""

import csv
import json
import os

from shopify.products import (
    fetch_all_products, fetch_product_metafields, missing_review_slots,
)
from features.seo_boost.injector import inject_product_seo
from features.seo_boost.runner import make_unique_title
from features.seo_boost.generator import generate_handle
from features.reviews.injector import inject_product_reviews
from features.fiche_produit.injector import inject_product_fiche
from utils.archive import latest_generated
from utils.logger import log


def _read_csv(store_path, name):
    path = os.path.join(store_path, "rapports", name)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _handle_map(base_url, headers):
    """{handle: product} pour tous les produits Shopify actuels."""
    return {p.get("handle"): p for p in fetch_all_products(base_url, headers)}


def _seo_alias_map(store_path):
    """{handle: autre_handle} (original↔nouveau) depuis le CSV SEO, pour retrouver
    un produit dont le handle a changé."""
    alias = {}
    for r in _read_csv(store_path, "seo_boost_preview.csv"):
        o, n = (r.get("handle_original") or "").strip(), (r.get("handle_nouveau") or "").strip()
        if o and n:
            alias[o] = n
            alias[n] = o
    return alias


def seo_data_from_row(row):
    """Reconstruit seo_data pour inject_product_seo depuis une ligne du CSV SEO."""
    return {
        "h1":               (row.get("h1_nouveau") or "").strip(),
        "meta_title":       (row.get("meta_title") or "").strip(),
        "handle_nouveau":   (row.get("handle_nouveau") or "").strip(),
        "meta_description": (row.get("meta_description") or "").strip(),
        "description_html": row.get("description_html") or "",
        "caracteristique":  "",   # non sauvegardé dans le CSV d'aperçu
    }


def reviews_from_row(row):
    """(note_globale, [reviews]) depuis une ligne du CSV reviews."""
    rating = (row.get("rating_global") or "").strip()
    count  = (row.get("review_count") or "").strip()
    note_globale = f"<strong>{rating}</strong> | {count}+ avis vérifiés"
    reviews = []
    for i in range(1, 9):
        titre = (row.get(f"review{i}_title") or "").strip()
        texte = (row.get(f"review{i}_text") or "").strip()
        if not (titre or texte):
            continue
        reviews.append({
            "note":       (row.get(f"review{i}_rating") or "5").strip(),
            "titre":      titre,
            "texte":      texte,
            "nom_auteur": (row.get(f"review{i}_author") or "").strip(),
        })
    return note_globale, reviews


def _find_product(by_handle, alias, *handles):
    """Retrouve un produit par ses handles possibles (+ alias original↔nouveau)."""
    for h in handles:
        h = (h or "").strip()
        if not h:
            continue
        if h in by_handle:
            return by_handle[h]
        alt = alias.get(h)
        if alt and alt in by_handle:
            return by_handle[alt]
    return None


# ── Push depuis l'archive permanente (data COMPLÈTE, prioritaire) ─────────────

def _read_title_attributes(store_path):
    """Lit seo_boost.title_attributes depuis config.json (pour respecter les cases cochées)."""
    try:
        with open(os.path.join(store_path, "config.json"), encoding="utf-8") as f:
            return json.load(f).get("seo_boost", {}).get("title_attributes")
    except (OSError, ValueError):
        return None


def _push_seo_from_archive(products_data, base_url, headers, title_attributes=None):
    """Re-injecte le SEO depuis l'archive (inclut les caractéristiques). Par ID produit.
    Dédoublonne les titres/handles au passage (en respectant les attributs cochés)
    → répare les URL en -1/-2 sans régénérer."""
    pushed = skipped = 0
    used_titles, used_handles = set(), set()
    # Amorçage anti-doublon par boutique : titres/handles des produits en ligne hors archive
    batch_ids = {(e.get("product") or {}).get("id") for e in products_data}
    try:
        for existing in fetch_all_products(base_url, headers):
            if existing.get("id") not in batch_ids:
                if existing.get("title"):
                    used_titles.add(existing["title"])
                if existing.get("handle"):
                    used_handles.add(existing["handle"])
    except Exception:
        pass
    for e in products_data:
        product, seo = e.get("product"), e.get("seo_data")
        if not (product and product.get("id") and seo):
            skipped += 1
            continue
        # Anti-doublon : titre unique → handle unique (au lieu du -N de Shopify)
        h1 = make_unique_title(seo.get("h1", ""), product.get("title", ""), used_titles, title_attributes)
        used_titles.add(h1)
        handle = generate_handle(h1)
        if handle in used_handles:
            base, k = handle, 2
            while f"{base}-{k}" in used_handles:
                k += 1
            handle = f"{base}-{k}"
        used_handles.add(handle)
        seo = {**seo, "h1": h1, "handle_nouveau": handle}
        try:
            inject_product_seo(
                product, seo, base_url, headers,
                generate_meta_desc=bool(seo.get("meta_description")),
                generate_description=bool(seo.get("description_html")),
            )
            pushed += 1
        except Exception as ex:
            log(f"Push SEO (archive) échec — {product.get('handle')} | {ex}", "error", also_print=True)
            skipped += 1
    return {"feature": "seo_boost", "source": "archive", "pushed": pushed,
            "skipped": skipped, "not_found": 0, "total": len(products_data)}


def _push_fiche_from_archive(products_data, base_url, headers):
    """Re-injecte les fiches produit depuis l'archive (descriptions COMPLÈTES). Par ID."""
    pushed = skipped = 0
    for e in products_data:
        product, content = e.get("product"), e.get("content")
        if not (product and product.get("id") and content):
            skipped += 1
            continue
        try:
            inject_product_fiche(product, content, base_url, headers)
            pushed += 1
        except Exception as ex:
            log(f"Push Fiche (archive) échec — {product.get('handle')} | {ex}", "error", also_print=True)
            skipped += 1
    return {"feature": "fiche_produit", "source": "archive", "pushed": pushed,
            "skipped": skipped, "not_found": 0, "total": len(products_data)}


def _push_reviews_from_archive(products_data, base_url, headers):
    """Re-injecte les avis depuis l'archive. Recalcule les slots vides (pas de doublon)."""
    pushed = skipped = 0
    for e in products_data:
        product = e.get("product")
        reviews = e.get("reviews") or []
        if not (product and product.get("id") and reviews):
            skipped += 1
            continue
        try:
            metafields = fetch_product_metafields(product["id"], base_url, headers)
            missing    = missing_review_slots(metafields)
        except Exception:
            missing = list(range(1, 9))
        if not missing:
            skipped += 1
            continue
        n = min(len(reviews), len(missing))
        reviews_data = {
            "note_globale":  e.get("note_globale", ""),
            "reviews":       reviews[:n],
            "missing_slots": missing[:n],
        }
        try:
            inject_product_reviews(product, reviews_data, base_url, headers)
            pushed += 1
        except Exception as ex:
            log(f"Push Reviews (archive) échec — {product.get('handle')} | {ex}", "error", also_print=True)
            skipped += 1
    return {"feature": "reviews", "source": "archive", "pushed": pushed,
            "skipped": skipped, "not_found": 0, "total": len(products_data)}


# ── Push depuis les CSV d'aperçu (fallback, data partielle) ───────────────────

def push_seo_boost(store_path, base_url, headers):
    arch = latest_generated(store_path, "seo_boost")
    if arch and arch.get("products_data"):
        return _push_seo_from_archive(arch["products_data"], base_url, headers,
                                      _read_title_attributes(store_path))
    rows = _read_csv(store_path, "seo_boost_preview.csv")
    if not rows:
        return {"feature": "seo_boost", "pushed": 0, "skipped": 0, "not_found": 0, "total": 0}
    by_handle = _handle_map(base_url, headers)
    alias     = _seo_alias_map(store_path)
    pushed = not_found = skipped = 0
    for row in rows:
        product = _find_product(by_handle, alias, row.get("handle_nouveau"), row.get("handle_original"))
        if not product:
            not_found += 1
            continue
        seo_data = seo_data_from_row(row)
        try:
            inject_product_seo(
                product, seo_data, base_url, headers,
                generate_meta_desc=bool(seo_data["meta_description"]),
                generate_description=bool(seo_data["description_html"]),
            )
            pushed += 1
        except Exception as e:
            log(f"Push SEO échec — {product.get('handle')} | {e}", "error", also_print=True)
            skipped += 1
    return {"feature": "seo_boost", "pushed": pushed, "skipped": skipped, "not_found": not_found, "total": len(rows)}


def push_fiche_produit(store_path, base_url, headers):
    """Fiche Produit : re-poussable UNIQUEMENT depuis l'archive (le CSV d'aperçu a des
    descriptions tronquées). Sans archive → à relancer."""
    arch = latest_generated(store_path, "fiche_produit")
    if arch and arch.get("products_data"):
        return _push_fiche_from_archive(arch["products_data"], base_url, headers)
    return {"feature": "fiche_produit", "source": "none", "pushed": 0, "skipped": 0,
            "not_found": 0, "total": 0,
            "note": "Aucune archive — descriptions tronquées dans le CSV, relancer Fiche Produit."}


def push_reviews(store_path, base_url, headers):
    arch = latest_generated(store_path, "reviews")
    if arch and arch.get("products_data"):
        return _push_reviews_from_archive(arch["products_data"], base_url, headers)
    rows = _read_csv(store_path, "reviews_preview.csv")
    if not rows:
        return {"feature": "reviews", "pushed": 0, "skipped": 0, "not_found": 0, "total": 0}
    by_handle = _handle_map(base_url, headers)
    alias     = _seo_alias_map(store_path)
    pushed = not_found = skipped = 0
    for row in rows:
        product = _find_product(by_handle, alias, row.get("handle"))
        if not product:
            not_found += 1
            continue
        note_globale, reviews = reviews_from_row(row)
        if not reviews:
            skipped += 1
            continue
        # Ne remplit que les slots avis_client vides → évite les doublons.
        try:
            metafields = fetch_product_metafields(product["id"], base_url, headers)
            missing    = missing_review_slots(metafields)
        except Exception:
            missing = list(range(1, 9))
        if not missing:
            skipped += 1
            continue
        n = min(len(reviews), len(missing))
        reviews_data = {
            "note_globale":  note_globale,
            "reviews":       reviews[:n],
            "missing_slots": missing[:n],
        }
        try:
            inject_product_reviews(product, reviews_data, base_url, headers)
            pushed += 1
        except Exception as e:
            log(f"Push Reviews échec — {product.get('handle')} | {e}", "error", also_print=True)
            skipped += 1
    return {"feature": "reviews", "pushed": pushed, "skipped": skipped, "not_found": not_found, "total": len(rows)}


def push_all(store_path, base_url, headers, features=("seo_boost", "reviews")):
    """Pousse la data sauvegardée des features demandées. Retourne un récap par feature."""
    results = []
    if "seo_boost" in features:
        results.append(push_seo_boost(store_path, base_url, headers))
    if "fiche_produit" in features:
        results.append(push_fiche_produit(store_path, base_url, headers))
    if "reviews" in features:
        results.append(push_reviews(store_path, base_url, headers))
    return {"results": results}
