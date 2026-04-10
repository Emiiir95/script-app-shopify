#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Normalisation des produits Shopify.

Règles appliquées par produit/variante :
  Produit  : status → "active"
  Variante : price         → max(price, compare_at_price)
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


# Hex approximatif par couleur (clé en minuscules sans accents ni espaces inutiles)
# Utilisé lors de la création de nouveaux metaobjects shopify--color-pattern
_COULEUR_HEX = {
    # Couleurs existantes dans le store (hex synchronisés)
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
    # Couleurs manquantes à créer
    "bleu":          "#2B6CB0",
    "bois":          "#C4A265",
    "bois foncé":    "#7A4E2D",
    # Autres couleurs communes
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
}


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
            label = next((f["value"] for f in node["fields"] if f["key"] == "label"), None)
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

    Args:
        color_name : nom exact de la couleur (ex: "Gris foncé") — tel que dans l'option variante

    Returns:
        str GID du metaobject créé
    """
    hex_color = _COULEUR_HEX.get(color_name.strip().lower())
    handle    = _to_handle(color_name)
    fields    = [{"key": "label", "value": color_name}]
    if hex_color:
        fields.append({"key": "color", "value": hex_color})

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
    log(f"Metaobject couleur créé : {color_name!r} ({hex_color or 'sans hex'}) → {gid}")
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


def compute_variant_changes(variant):
    """
    Calcule les valeurs normalisées d'une variante sans rien écrire.

    Règle prix : si compare_at_price > price → price = compare_at_price
                 compare_at_price toujours vidé après.

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


def normalize_product(product, base_url, headers, vendor, category_gid=None, taxonomy_node_id=None, color_map=None, keep_status=False):
    """
    Normalise un produit et toutes ses variantes dans Shopify.

    Étapes :
      1. PUT product  → status + vendor = nom boutique
      2. GraphQL      → catégorie taxonomique (si category_gid fourni)
      3. Pour chaque variante → PUT variant avec prix normalisé + champs cibles
                              → GraphQL shopify.color-pattern (si option "Couleur" + color_map)

    Args:
        product      : dict Shopify avec "id", "handle", "status", "variants", "options"
        base_url     : URL de base REST Shopify
        headers      : dict des headers HTTP Shopify
        vendor       : nom de la boutique à injecter dans le champ vendor
        category_gid     : GID TaxonomyCategory (nouveau système) ou None
        taxonomy_node_id : GID ProductTaxonomyNode (repli si category_gid absent) ou None
        color_map        : dict { nom_couleur_lowercase: gid } issu de fetch_color_pattern_map()
                       ou None pour ne pas modifier le metafield couleur
        keep_status      : si True, garde le status actuel du produit au lieu de forcer "active"

    Returns:
        list de dicts — une entrée par variante avec les valeurs avant/après
    """
    product_id = product["id"]
    handle     = product.get("handle", "")
    variants   = product.get("variants", [])
    variant_results = []

    # ── Étape 1 : status + vendor produit (REST) ──────────────────────────────
    target_status = product.get("status", _TARGET_STATUS) if keep_status else _TARGET_STATUS
    product_update = {"id": product_id, "status": target_status, "vendor": vendor}
    shopify_put(
        f"{base_url}/products/{product_id}.json",
        headers,
        {"product": product_update},
    )
    log(f"Produit mis à jour — {handle} | status: {target_status} | vendor: {vendor!r}")

    # ── Étape 2 : catégorie taxonomique (GraphQL) ─────────────────────────────
    effective_category = category_gid or taxonomy_node_id
    if effective_category:
        _set_product_category(product_id, effective_category, base_url, headers)
        log(f"Catégorie définie — {handle} | {effective_category}")

    # ── Étape 3 : variantes (REST) ───────────────────────────────────────────
    for variant in variants:
        variant_id  = variant["id"]
        sku         = variant.get("sku", "")
        changes     = compute_variant_changes(variant)

        shopify_put(
            f"{base_url}/variants/{variant_id}.json",
            headers,
            {
                "variant": {
                    "id":                  variant_id,
                    "price":               changes["prix_apres"],
                    "compare_at_price":    None,
                    "taxable":             _TARGET_TAXABLE,
                    "inventory_policy":    _TARGET_INVENTORY_POLICY,
                    "fulfillment_service": _TARGET_FULFILLMENT_SERVICE,
                    "requires_shipping":   _TARGET_REQUIRES_SHIPPING,
                }
            },
        )
        log(
            f"Variante normalisée — {handle} | SKU: {sku!r} | "
            f"prix {changes['prix_avant']} → {changes['prix_apres']} | "
            f"compare_at {changes['compare_at_avant']} → null"
        )

        variant_results.append({
            "handle":         handle,
            "titre_produit":  product.get("title", ""),
            "sku":            sku,
            "prix_avant":     changes["prix_avant"],
            "compare_at_avant": changes["compare_at_avant"],
            "prix_apres":     changes["prix_apres"],
        })

    # ── Étape 4 : liaison option Couleur → shopify.color-pattern (GraphQL) ───
    if color_map:
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
