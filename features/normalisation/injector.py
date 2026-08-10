#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Normalisation des produits Shopify.

Règles appliquées par produit/variante :
  Produit  : status → "active"
  Variante : price         → selon price_mode (keep_price | use_compare | max)
             compare_at_price → null (toujours vidé)
             taxable            → false
             inventory_policy   → "deny"
             fulfillment_service → "manual"
             requires_shipping  → true

Fonctions publiques :
  - compute_variant_changes(variant)             : calcule les changements sans écrire
  - normalize_product(product, base_url, headers): injecte les changements dans Shopify
  - generate_injection_report(log, store_path)   : CSV post-injection horodaté
"""

import csv
import json
import os
import re
import unicodedata
from datetime import datetime

from shopify.client import shopify_put, graphql_request
from utils.logger import log


# Valeurs cibles — source de vérité unique
_TARGET_TAXABLE             = False
_TARGET_INVENTORY_POLICY    = "deny"
_TARGET_FULFILLMENT_SERVICE = "manual"
_TARGET_REQUIRES_SHIPPING   = True
_TARGET_STATUS              = "active"


# Hex par couleur (clé en minuscules) — pour le champ optionnel "color"
_COULEUR_HEX = {
    "beige":         "#EAD8AB",
    "blanc":         "#FFFFFF",
    "noir":          "#000000",
    "gris":          "#808080",
    "gris foncé":    "#555555",
    "gris clair":    "#C0C0C0",
    "rose":          "#FFC0CB",
    "violet":        "#A54DCF",
    "marron":        "#9A5630",
    "vert":          "#05AA3D",
    "bleu":          "#2B6CB0",
    "bois":          "#C4A265",
    "bois foncé":    "#7A4E2D",
    "rouge":         "#E63946",
    "bleu marine":   "#1A3A5C",
    "bleu clair":    "#7EC8E3",
    "vert foncé":    "#1B4332",
    "vert clair":    "#90EE90",
    "jaune":         "#FFD700",
    "orange":        "#F97316",
    "rose clair":    "#FFB6C1",
    "marron rouge":  "#8B3A3A",
    "naturel":       "#D4B896",
    "crème":         "#FFF8DC",
    "ivoire":        "#FFFFF0",
    "taupe":         "#8B7D6B",
    "caramel":       "#C68642",
    "doré":          "#FFD700",
    "argenté":       "#C0C0C0",
    "multicolore":   "#FF6B6B",
    "noël":          "#C41E3A",
}

# GIDs taxonomiques Shopify pour color_taxonomy_reference (standardisés par Shopify)
# Source : gid://shopify/TaxonomyValue/{id}
_COULEUR_TAXONOMY_GID = {
    "noir":          "gid://shopify/TaxonomyValue/1",   # Black
    "bleu":          "gid://shopify/TaxonomyValue/2",   # Blue
    "bleu marine":   "gid://shopify/TaxonomyValue/15",  # Navy
    "blanc":         "gid://shopify/TaxonomyValue/3",   # White
    "doré":          "gid://shopify/TaxonomyValue/4",   # Gold
    "argenté":       "gid://shopify/TaxonomyValue/5",   # Silver
    "beige":         "gid://shopify/TaxonomyValue/6",   # Beige
    "marron":        "gid://shopify/TaxonomyValue/7",   # Brown
    "bois":          "gid://shopify/TaxonomyValue/7",   # Brown
    "bois foncé":    "gid://shopify/TaxonomyValue/7",   # Brown
    "caramel":       "gid://shopify/TaxonomyValue/7",   # Brown
    "gris":          "gid://shopify/TaxonomyValue/8",   # Gray
    "gris foncé":    "gid://shopify/TaxonomyValue/8",   # Gray
    "gris clair":    "gid://shopify/TaxonomyValue/8",   # Gray
    "vert":          "gid://shopify/TaxonomyValue/9",   # Green
    "vert foncé":    "gid://shopify/TaxonomyValue/9",   # Green
    "vert clair":    "gid://shopify/TaxonomyValue/9",   # Green
    "orange":        "gid://shopify/TaxonomyValue/10",  # Orange
    "rose":          "gid://shopify/TaxonomyValue/11",  # Pink
    "rose clair":    "gid://shopify/TaxonomyValue/11",  # Pink
    "violet":        "gid://shopify/TaxonomyValue/12",  # Purple
    "rouge":         "gid://shopify/TaxonomyValue/13",  # Red
    "noël":          "gid://shopify/TaxonomyValue/13",  # Red
    "marron rouge":  "gid://shopify/TaxonomyValue/13",  # Red
    "jaune":         "gid://shopify/TaxonomyValue/14",  # Yellow
    "multicolore":   "gid://shopify/TaxonomyValue/13",  # Red (fallback)
    "naturel":       "gid://shopify/TaxonomyValue/6",   # Beige
    "crème":         "gid://shopify/TaxonomyValue/6",   # Beige
    "ivoire":        "gid://shopify/TaxonomyValue/3",   # White
    "taupe":         "gid://shopify/TaxonomyValue/8",   # Gray
}

# GID taxonomique pour le motif "Solid" (universel — même valeur pour tous les motifs unis)
_PATTERN_SOLID_GID = "gid://shopify/TaxonomyValue/2874"


def _to_handle(text):
    """Convertit un nom de couleur en handle slug pour les metaobjects."""
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return f"couleur-{text}"



def find_taxonomy_category_gid(category_name, base_url, headers):
    """
    Recherche le GID TaxonomyCategory par nom dans la taxonomie Shopify.

    Returns:
        str GID (ex: "gid://shopify/TaxonomyCategory/aa-7") ou None si non trouvé.
    """
    query = """
query($search: String!) {
  taxonomy {
    categories(search: $search, first: 10) {
      nodes { id name isLeaf }
    }
  }
}"""
    data  = graphql_request(base_url, headers, query, {"search": category_name})
    nodes = data.get("data", {}).get("taxonomy", {}).get("categories", {}).get("nodes", [])
    # Priorité : correspondance exacte sur le nom
    for node in nodes:
        if node.get("name", "").strip().lower() == category_name.strip().lower():
            return node["id"]
    # Fallback : première feuille retournée
    for node in nodes:
        if node.get("isLeaf"):
            return node["id"]
    return None


def search_taxonomy_categories(term, base_url, headers, first=10):
    """
    Recherche des catégories dans la taxonomie Shopify et retourne les candidats.

    Returns:
        list de dicts { id, name, fullName, isLeaf } (peut être vide).
        `fullName` = chemin complet (ex: "Boîtes à bijoux dans Présentoirs à bijoux").
    """
    query = """
query($search: String!, $first: Int!) {
  taxonomy {
    categories(search: $search, first: $first) {
      nodes { id name fullName isLeaf }
    }
  }
}"""
    data  = graphql_request(base_url, headers, query, {"search": term, "first": first})
    return data.get("data", {}).get("taxonomy", {}).get("categories", {}).get("nodes", []) or []


# Mots vides ignorés pour générer les mots-clés de match depuis une niche
_NICHE_STOPWORDS = {
    "a", "au", "aux", "avec", "de", "des", "du", "en", "et", "la", "le", "les",
    "pour", "sur", "un", "une",
}


def niche_to_match_keywords(niche):
    """
    Transforme un nom de niche en un mot-clé de match multi-mots.

    Ex : "Boîte à Montre" → ["boite montre"] (exige boite ET montre à la fois).
    Les mots vides (à, de, le…) sont retirés. Retourne une liste à 1 élément
    (le mot-clé multi-mots) — cohérent avec la sémantique « tous les mots présents ».
    """
    words = [w for w in _norm_cat_text(niche).split() if w not in _NICHE_STOPWORDS]
    return [" ".join(words)] if words else []


def _score_candidate(node, niche_words):
    """Score un candidat taxonomie : + si feuille, + par mot de la niche présent dans le nom."""
    name_words = set(_norm_cat_text(node.get("name", "")).split())
    overlap    = len(name_words & niche_words)
    return overlap * 2 + (1 if node.get("isLeaf") else 0)


def suggest_categories_for_niches(niches, base_url, headers):
    """
    Pour chaque niche, cherche la meilleure catégorie Shopify et construit une règle.

    Pour chaque niche :
      1. Génère les mots-clés de match (niche_to_match_keywords).
      2. Cherche dans la taxonomie (search_taxonomy_categories) avec le nom de la niche.
      3. Choisit le meilleur candidat (chevauchement de mots + feuille).

    Args:
        niches   : liste de noms de niches (str), ex: seo_boost.niches
        base_url : URL de base REST Shopify
        headers  : dict des headers HTTP Shopify

    Returns:
        list de dicts { match, name, search, gid, fullName, found, niche } — une par niche.
        `name` = catégorie proposée (français, telle que renvoyée par Shopify) ou la niche
        elle-même si rien trouvé (found=False). `search` reste vide (recherche par name).
    """
    rules = []
    for niche in niches:
        niche = (niche or "").strip()
        if not niche:
            continue
        match       = niche_to_match_keywords(niche)
        niche_words = set(_norm_cat_text(niche).split()) - _NICHE_STOPWORDS
        try:
            candidates = search_taxonomy_categories(niche, base_url, headers)
        except Exception as e:
            log(f"Recherche catégorie échouée pour {niche!r} : {e}", "warning")
            candidates = []

        best = None
        if candidates:
            best = max(candidates, key=lambda n: _score_candidate(n, niche_words))

        if best:
            rules.append({
                "match":    match,
                "name":     best.get("name", niche),
                "search":   "",
                "gid":      best.get("id"),
                "fullName": best.get("fullName", ""),
                "found":    True,
                "niche":    niche,
            })
        else:
            rules.append({
                "match":    match,
                "name":     niche,
                "search":   "",
                "gid":      None,
                "fullName": "",
                "found":    False,
                "niche":    niche,
            })
    # Le plus spécifique d'abord (plus de mots-clés = priorité) — sécurité d'ordre
    rules.sort(key=lambda r: -len((r["match"][0] if r["match"] else "").split()))
    return rules


def _norm_cat_text(text):
    """Normalise un texte pour le matching de catégorie : sans accent, minuscules,
    ponctuation → espaces, espaces multiples réduits."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    text = text.lower()
    text = re.sub(r"[^a-z0-9]+", " ", text)
    return f" {text.strip()} "   # espaces autour → match de mot entier avec ' kw '


def match_category_rule(product, rules):
    """
    Détermine la règle de catégorie qui s'applique à un produit (boutique thématique).

    Pour chaque règle (dans l'ordre), on teste ses mots-clés (`match`) contre le
    titre + product_type + tags du produit. Un mot-clé matche si **TOUS ses mots**
    sont présents (mots entiers, sans accent/casse) — donc un mot-clé multi-mots
    comme "boîte montre" exige `boite` ET `montre` (dans n'importe quel ordre), ce
    qui distingue « Boîte à Montre » de « Boîte à Bijoux ». La PREMIÈRE règle dont
    un mot-clé matche gagne (l'ordre = priorité).

    Si une règle n'a pas de `match`, son `name` sert de mot-clé.

    Args:
        product : dict Shopify (title, product_type, tags)
        rules   : liste de dicts { match: [str], name: str, search: str, _gid: str }

    Returns:
        La règle qui matche (dict) ou None si aucune.
    """
    if not rules:
        return None

    tags = product.get("tags", "")
    if isinstance(tags, list):
        tags = " ".join(tags)
    haystack_words = set(_norm_cat_text(
        f"{product.get('title', '')} {product.get('product_type', '')} {tags}"
    ).split())

    for rule in rules:
        keywords = rule.get("match") or ([rule["name"]] if rule.get("name") else [])
        for kw in keywords:
            words = _norm_cat_text(kw).split()
            if words and all(w in haystack_words for w in words):
                return rule
    return None


def resolve_rule_gids(rules, base_url, headers):
    """
    Résout le GID taxonomique de chaque règle de catégorie (une seule fois par terme).

    Le terme cherché est `search` s'il est fourni, sinon `name` (saisi en français —
    la taxonomie Shopify renvoie les noms dans la langue de la boutique). Ajoute la
    clé `_gid` à chaque règle (None si le terme est introuvable).

    Args:
        rules    : liste de dicts { match, name, search? }
        base_url : URL de base REST Shopify
        headers  : dict des headers HTTP Shopify

    Returns:
        La même liste, chaque règle enrichie de `_gid`.
    """
    cache = {}
    for rule in rules:
        # GID explicite (fourni par le bouton « Récupérer les catégories ») → direct,
        # aucune recherche nécessaire (les GID de catégorie sont universels).
        if rule.get("gid"):
            rule["_gid"] = rule["gid"]
            continue
        term = (rule.get("search") or rule.get("name") or "").strip()
        if not term:
            rule["_gid"] = None
            continue
        if term not in cache:
            cache[term] = find_taxonomy_category_gid(term, base_url, headers)
        rule["_gid"] = cache[term]
        if not rule["_gid"]:
            log(f"Catégorie introuvable dans la taxonomie Shopify : {term!r}", "warning")
    return rules


def _set_product_category(product_id, category_gid, base_url, headers):
    """Définit la catégorie taxonomique d'un produit via GraphQL (TaxonomyCategory GID)."""
    query = """
mutation productUpdate($input: ProductInput!) {
  productUpdate(input: $input) {
    product { id }
    userErrors { field message }
  }
}"""
    variables = {
        "input": {
            "id": f"gid://shopify/Product/{product_id}",
            "category": category_gid,
        }
    }
    data = graphql_request(base_url, headers, query, variables)
    errors = data.get("data", {}).get("productUpdate", {}).get("userErrors", [])
    if errors:
        raise Exception(f"Catégorie GraphQL — userErrors: {errors}")


def fetch_color_pattern_map(base_url, headers):
    """
    Récupère tous les metaobjects shopify--color-pattern et retourne
    un dict { nom_couleur_lowercase: gid }.

    Utilisé pour résoudre la valeur texte de l'option "Couleur" en GID
    avant d'écrire le metafield shopify.color-pattern (list.metaobject_reference).
    """
    query = """
query($cursor: String) {
  metaobjects(type: "shopify--color-pattern", first: 250, after: $cursor) {
    nodes {
      id
      fields { key value }
    }
    pageInfo { hasNextPage endCursor }
  }
}"""
    color_map = {}
    cursor    = None
    while True:
        data  = graphql_request(base_url, headers, query, {"cursor": cursor})
        mo    = data.get("data", {}).get("metaobjects", {})
        for node in mo.get("nodes", []):
            fields_map = {f["key"]: f["value"] for f in node["fields"]}
            # label en priorité, sinon base_pattern comme nom de référence
            label = fields_map.get("label") or fields_map.get("base_pattern")
            if label:
                color_map[label.strip().lower()] = node["id"]
        page_info = mo.get("pageInfo", {})
        if not page_info.get("hasNextPage"):
            break
        cursor = page_info["endCursor"]

    log(f"Color pattern map chargé — {len(color_map)} entrée(s)")
    return color_map


def create_color_pattern_metaobject(color_name, base_url, headers):
    """
    Crée un metaobject shopify--color-pattern pour une couleur manquante.

    Type standard Shopify (pas Combined Listings) — champs :
      - label : nom affiché (single_line_text_field)
      - color : hex de la couleur (color)

    Args:
        color_name : nom exact de la couleur (ex: "Gris foncé") — tel que dans l'option variante

    Returns:
        str GID du metaobject créé
    """
    key       = color_name.strip().lower()
    hex_color = _COULEUR_HEX.get(key, "#808080")
    color_gid = _COULEUR_TAXONOMY_GID.get(key, "gid://shopify/TaxonomyValue/8")  # Gray par défaut
    handle    = _to_handle(color_name)

    # color_taxonomy_reference attend une liste JSON de GIDs
    fields = [
        {"key": "label",                     "value": color_name},
        {"key": "color",                     "value": hex_color},
        {"key": "color_taxonomy_reference",  "value": json.dumps([color_gid])},
        {"key": "pattern_taxonomy_reference", "value": _PATTERN_SOLID_GID},
    ]

    query = """
mutation metaobjectCreate($metaobject: MetaobjectCreateInput!) {
  metaobjectCreate(metaobject: $metaobject) {
    metaobject { id handle }
    userErrors { field message code }
  }
}"""
    variables = {
        "metaobject": {
            "type":   "shopify--color-pattern",
            "handle": handle,
            "fields": fields,
        }
    }
    data   = graphql_request(base_url, headers, query, variables)
    result = data.get("data", {}).get("metaobjectCreate", {})
    errors = result.get("userErrors", [])
    if errors:
        raise Exception(f"Création couleur {color_name!r} — userErrors: {errors}")
    gid = result.get("metaobject", {}).get("id")
    log(f"Metaobject couleur créé : {color_name!r} ({hex_color} | taxonomy: {color_gid}) → {gid}")
    return gid


def _fetch_product_options_gql(product_id, base_url, headers):
    """
    Récupère via GraphQL les options d'un produit avec leurs IDs et valeurs.

    Returns:
        list de dicts { id, name, position, optionValues: [{ id, name }] }
    """
    query = """
query($id: ID!) {
  product(id: $id) {
    options {
      id
      name
      position
      optionValues {
        id
        name
      }
    }
  }
}"""
    data = graphql_request(base_url, headers, query, {"id": f"gid://shopify/Product/{product_id}"})
    return data.get("data", {}).get("product", {}).get("options", [])


def _link_couleur_option_to_color_pattern(product_id, option_gid, option_values, color_map, base_url, headers):
    """
    Lie l'option 'Couleur' au metafield shopify.color-pattern via productOptionUpdate.

    Étapes :
      1. Définit linkedMetafield { namespace: "shopify", key: "color-pattern" } sur l'option
      2. Met à jour chaque valeur d'option avec son linkedMetafieldValue (GID metaobject)

    Args:
        product_id   : ID REST du produit (int)
        option_gid   : GID GraphQL de l'option Couleur (str)
        option_values: list de dicts { id: GID, name: str } issus de _fetch_product_options_gql
        color_map    : dict { nom_couleur_lowercase: gid_metaobject }
    """
    values_to_update = []
    for ov in option_values:
        color_gid = color_map.get(ov["name"].strip().lower())
        if color_gid:
            values_to_update.append({
                "id":                   ov["id"],
                "linkedMetafieldValue": color_gid,
            })

    if not values_to_update:
        log(f"Aucune valeur Couleur à lier pour le produit {product_id}", "warning")
        return

    query = """
mutation productOptionUpdate(
  $productId: ID!
  $option: OptionUpdateInput!
  $optionValuesToUpdate: [OptionValueUpdateInput!]
) {
  productOptionUpdate(
    productId: $productId
    option: $option
    optionValuesToUpdate: $optionValuesToUpdate
  ) {
    product {
      options {
        id
        name
        optionValues { id name linkedMetafieldValue }
      }
    }
    userErrors { field message }
  }
}"""
    variables = {
        "productId":           f"gid://shopify/Product/{product_id}",
        "option": {
            "id":            option_gid,
            "linkedMetafield": {
                "namespace": "shopify",
                "key":       "color-pattern",
            },
        },
        "optionValuesToUpdate": values_to_update,
    }
    data   = graphql_request(base_url, headers, query, variables)
    errors = data.get("data", {}).get("productOptionUpdate", {}).get("userErrors", [])
    if errors:
        raise Exception(f"productOptionUpdate couleur — userErrors: {errors}")
    log(f"Option Couleur liée — produit {product_id} | {len(values_to_update)} valeur(s) connectée(s)")


def compute_variant_changes(variant, price_mode="max"):
    """
    Calcule les valeurs normalisées d'une variante sans rien écrire.

    Le prix barré (compare_at_price) est TOUJOURS vidé. Le prix final dépend de
    price_mode :
      - "keep_price"  : garde le prix actuel (price)            → ex 20 / barré 50 → 20
      - "use_compare" : met le prix barré comme prix            → ex 20 / barré 50 → 50
                        (sécurité : si pas de barré, garde price, jamais 0)
      - "max" (défaut): garde le plus élevé des deux            → ex 20 / barré 50 → 50

    Returns:
        dict avec :
          "prix_avant", "compare_at_avant",
          "prix_apres"  (nouveau price à appliquer),
          "changed"     (bool — True si au moins un champ change)
    """
    price_str      = variant.get("price") or "0"
    compare_str    = variant.get("compare_at_price") or "0"

    try:
        price      = float(price_str)
        compare_at = float(compare_str)
    except (ValueError, TypeError):
        price      = 0.0
        compare_at = 0.0

    if price_mode == "keep_price":
        new_price = price
    elif price_mode == "use_compare":
        new_price = compare_at if compare_at > 0 else price   # jamais mettre le prix à 0
    else:  # "max" (défaut)
        new_price = compare_at if compare_at > price else price

    # Détecter si quelque chose change
    price_changed   = abs(new_price - price) > 0.001
    compare_changed = compare_at != 0.0  # on vide toujours compare_at
    field_changed   = (
        bool(variant.get("taxable"))            != _TARGET_TAXABLE or
        variant.get("inventory_policy")          != _TARGET_INVENTORY_POLICY or
        variant.get("fulfillment_service")       != _TARGET_FULFILLMENT_SERVICE or
        bool(variant.get("requires_shipping"))   != _TARGET_REQUIRES_SHIPPING
    )

    return {
        "prix_avant":     price_str,
        "compare_at_avant": compare_str,
        "prix_apres":     f"{new_price:.2f}",
        "changed":        price_changed or compare_changed or field_changed,
    }


def resolve_steps(steps):
    """
    Normalise le dict des parties activées de la normalisation.

    Chaque partie est activée par défaut (clé absente/None → True) pour rester
    100 % rétrocompatible avec les configs qui n'ont pas de bloc `steps`.

    Parties reconnues :
      - "prix"        : prix + prix barré (compare_at_price)
      - "stock_taxes" : taxable, inventory_policy, fulfillment_service, requires_shipping
      - "fournisseur" : vendor = nom boutique
      - "categorie"   : catégorie taxonomique Shopify
      - "couleurs"    : swatches shopify--color-pattern liés aux variantes

    Returns:
        dict { partie: bool } avec les 5 clés toujours présentes.
    """
    steps = steps or {}
    keys  = ("prix", "stock_taxes", "fournisseur", "categorie", "couleurs")
    return {k: steps.get(k, True) is not False for k in keys}


def normalize_product(product, base_url, headers, vendor, category_gid=None, taxonomy_node_id=None, color_map=None, price_mode="max", steps=None):
    """
    Normalise un produit et toutes ses variantes dans Shopify.

    Étapes (chacune ne s'exécute que si activée dans `steps`) :
      1. PUT product  → vendor = nom boutique (partie "fournisseur"). Le status est
                        toujours préservé — la normalisation ne le change jamais.
      2. GraphQL      → catégorie taxonomique (partie "categorie", si category_gid fourni)
      3. Pour chaque variante → PUT variant : prix normalisé (partie "prix") et/ou
                        champs stock/taxes/livraison (partie "stock_taxes")
                              → GraphQL shopify.color-pattern (partie "couleurs", si color_map)

    Args:
        product      : dict Shopify avec "id", "handle", "status", "variants", "options"
        base_url     : URL de base REST Shopify
        headers      : dict des headers HTTP Shopify
        vendor       : nom de la boutique à injecter dans le champ vendor
        category_gid     : GID TaxonomyCategory (nouveau système) ou None
        taxonomy_node_id : GID ProductTaxonomyNode (repli si category_gid absent) ou None
        color_map        : dict { nom_couleur_lowercase: gid } issu de fetch_color_pattern_map()
                       ou None pour ne pas modifier le metafield couleur
        steps        : dict { partie: bool } — voir resolve_steps(). None → tout activé.

    Returns:
        list de dicts — une entrée par variante avec les valeurs avant/après
    """
    on = resolve_steps(steps)
    product_id = product["id"]
    handle     = product.get("handle", "")
    variants   = product.get("variants", [])
    variant_results = []

    # ── Étape 1 : vendor produit (REST) — partie "fournisseur" ────────────────
    # Le status est toujours préservé — la normalisation ne change jamais le status
    target_status = product.get("status", "draft")
    if on["fournisseur"]:
        shopify_put(
            f"{base_url}/products/{product_id}.json",
            headers,
            {"product": {"id": product_id, "status": target_status, "vendor": vendor}},
        )
        log(f"Produit mis à jour — {handle} | status: {target_status} | vendor: {vendor!r}")

    # ── Étape 2 : catégorie taxonomique (GraphQL) — partie "categorie" ────────
    effective_category = category_gid or taxonomy_node_id
    if on["categorie"] and effective_category:
        _set_product_category(product_id, effective_category, base_url, headers)
        log(f"Catégorie définie — {handle} | {effective_category}")

    # ── Étape 3 : variantes (REST) — parties "prix" et "stock_taxes" ─────────
    for variant in variants:
        variant_id  = variant["id"]
        sku         = variant.get("sku", "")
        changes     = compute_variant_changes(variant, price_mode)

        variant_payload = {"id": variant_id}
        if on["prix"]:
            variant_payload["price"]            = changes["prix_apres"]
            variant_payload["compare_at_price"] = None
        if on["stock_taxes"]:
            variant_payload["taxable"]             = _TARGET_TAXABLE
            variant_payload["inventory_policy"]    = _TARGET_INVENTORY_POLICY
            variant_payload["fulfillment_service"] = _TARGET_FULFILLMENT_SERVICE
            variant_payload["requires_shipping"]   = _TARGET_REQUIRES_SHIPPING

        if len(variant_payload) > 1:   # au moins un champ à écrire (en plus de l'id)
            shopify_put(
                f"{base_url}/variants/{variant_id}.json",
                headers,
                {"variant": variant_payload},
            )
            log(
                f"Variante normalisée — {handle} | SKU: {sku!r} | "
                f"prix {changes['prix_avant']} → "
                f"{changes['prix_apres'] if on['prix'] else changes['prix_avant']}"
                + (f" | compare_at {changes['compare_at_avant']} → null" if on["prix"] else "")
            )

        variant_results.append({
            "handle":         handle,
            "titre_produit":  product.get("title", ""),
            "sku":            sku,
            "prix_avant":     changes["prix_avant"],
            "compare_at_avant": changes["compare_at_avant"],
            "prix_apres":     changes["prix_apres"] if on["prix"] else changes["prix_avant"],
        })

    # ── Étape 4 : liaison option Couleur → shopify.color-pattern (GraphQL) ───
    if on["couleurs"] and color_map:
        options_gql = _fetch_product_options_gql(product_id, base_url, headers)
        couleur_opt = next(
            (o for o in options_gql if o.get("name", "").strip().lower() == "couleur"),
            None,
        )
        if couleur_opt:
            _link_couleur_option_to_color_pattern(
                product_id,
                couleur_opt["id"],
                couleur_opt.get("optionValues", []),
                color_map,
                base_url,
                headers,
            )
            log(f"Couleur option liée — {handle}")
        else:
            log(f"Option Couleur absente — {handle} (liaison couleur ignorée)")

    return variant_results


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-normalisation.

    Colonnes :
        date_heure, handle, titre_produit, sku,
        prix_avant, compare_at_avant, prix_apres,
        statut, erreur

    Returns:
        str : chemin absolu du rapport généré
    """
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", f"normalisation_rapport_{timestamp}.csv")
    fieldnames = [
        "date_heure", "handle", "titre_produit", "sku",
        "prix_avant", "compare_at_avant", "prix_apres",
        "statut", "erreur",
    ]
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            writer.writerow({
                "date_heure":       now_str,
                "handle":           entry.get("handle", ""),
                "titre_produit":    entry.get("titre_produit", ""),
                "sku":              entry.get("sku", ""),
                "prix_avant":       entry.get("prix_avant", ""),
                "compare_at_avant": entry.get("compare_at_avant", ""),
                "prix_apres":       entry.get("prix_apres", ""),
                "statut":           entry.get("statut", ""),
                "erreur":           entry.get("erreur", ""),
            })

    log(f"Rapport normalisation généré : {csv_path}")
    print(f"\n[RAPPORT] CSV : {csv_path}")
    return csv_path
