"""
exporter.py — Lecture complète d'un store Shopify source.

Exporte :
  - Metaobject definitions (structure + champs)
  - Metaobjects (instances avec valeurs)
  - Metafield definitions (product, namespace custom)
  - Produits (tous champs, images, variantes)
  - Metafields produit (namespace custom, avec type)
"""

from tqdm import tqdm

from shopify.client import shopify_get, shopify_get_paginated, graphql_request
from utils.logger import log


# ── Metaobject Definitions ────────────────────────────────────────────────────

def export_metaobject_definitions(base_url, headers):
    """Retourne toutes les metaobject definitions avec leurs field definitions."""
    query = """
    query GetMetaobjectDefinitions($cursor: String) {
      metaobjectDefinitions(first: 50, after: $cursor) {
        edges {
          node {
            id
            type
            name
            fieldDefinitions {
              key
              name
              type { name }
              required
              validations { name value }
            }
          }
          cursor
        }
        pageInfo { hasNextPage }
      }
    }
    """
    results = []
    cursor = None

    while True:
        variables = {"cursor": cursor} if cursor else {}
        data = graphql_request(base_url, headers, query, variables)
        edges = data.get("data", {}).get("metaobjectDefinitions", {}).get("edges", [])
        page_info = data.get("data", {}).get("metaobjectDefinitions", {}).get("pageInfo", {})

        for edge in edges:
            node = edge["node"]
            cursor = edge.get("cursor")
            results.append({
                "source_id": node["id"],
                "type": node["type"],
                "name": node["name"],
                "fieldDefinitions": [
                    {
                        "key": fd["key"],
                        "name": fd["name"],
                        "type": fd["type"]["name"],
                        "required": fd.get("required", False),
                        "validations": fd.get("validations", []),
                    }
                    for fd in node.get("fieldDefinitions", [])
                ],
            })

        if not page_info.get("hasNextPage"):
            break

    log(f"Export — {len(results)} metaobject definition(s)")
    return results


# ── Metaobjects (instances) ───────────────────────────────────────────────────

def export_metaobjects(base_url, headers, definition_types):
    """Retourne tous les metaobjects groupés par type."""
    query = """
    query GetMetaobjects($type: String!, $cursor: String) {
      metaobjects(type: $type, first: 50, after: $cursor) {
        edges {
          node {
            id
            type
            handle
            fields {
              key
              value
              type
            }
          }
          cursor
        }
        pageInfo { hasNextPage }
      }
    }
    """
    result = {}

    for type_key in definition_types:
        instances = []
        cursor = None

        while True:
            variables = {"type": type_key}
            if cursor:
                variables["cursor"] = cursor

            data = graphql_request(base_url, headers, query, variables)
            edges = data.get("data", {}).get("metaobjects", {}).get("edges", [])
            page_info = data.get("data", {}).get("metaobjects", {}).get("pageInfo", {})

            for edge in edges:
                node = edge["node"]
                cursor = edge.get("cursor")
                instances.append({
                    "source_id": node["id"],
                    "handle": node.get("handle", ""),
                    "type": node["type"],
                    "fields": [
                        {"key": f["key"], "value": f["value"], "type": f["type"]}
                        for f in node.get("fields", [])
                    ],
                })

            if not page_info.get("hasNextPage"):
                break

        result[type_key] = instances
        log(f"Export — {len(instances)} metaobject(s) de type '{type_key}'")

    return result


# ── Metafield Definitions (product, namespace custom) ─────────────────────────

def export_metafield_definitions(base_url, headers):
    """Retourne toutes les metafield definitions de type PRODUCT, namespace custom."""
    query = """
    query GetMetafieldDefinitions($cursor: String) {
      metafieldDefinitions(
        ownerType: PRODUCT
        namespace: "custom"
        first: 50
        after: $cursor
      ) {
        edges {
          node {
            id
            name
            namespace
            key
            type { name }
            validations { name value }
          }
          cursor
        }
        pageInfo { hasNextPage }
      }
    }
    """
    results = []
    cursor = None

    while True:
        variables = {"cursor": cursor} if cursor else {}
        data = graphql_request(base_url, headers, query, variables)
        edges = data.get("data", {}).get("metafieldDefinitions", {}).get("edges", [])
        page_info = data.get("data", {}).get("metafieldDefinitions", {}).get("pageInfo", {})

        for edge in edges:
            node = edge["node"]
            cursor = edge.get("cursor")
            results.append({
                "source_id": node["id"],
                "name": node["name"],
                "namespace": node["namespace"],
                "key": node["key"],
                "type": node["type"]["name"],
                "validations": node.get("validations", []),
            })

        if not page_info.get("hasNextPage"):
            break

    log(f"Export — {len(results)} metafield definition(s) product/custom")
    return results


# ── Produits (REST, tous champs) ──────────────────────────────────────────────

def export_products(base_url, headers):
    """Fetch tous les produits (active + draft + archived) pour le transfert."""
    all_products = []

    # L'API REST n'accepte pas status=any — il faut fetcher chaque status séparément.
    # Sans paramètre status, seuls les "active" sont retournés.
    for status in ("active", "draft", "archived"):
        url = f"{base_url}/products.json"
        params = {"limit": 250, "status": status}

        while url:
            data, link_header = shopify_get_paginated(url, headers, params=params)
            batch = data.get("products", [])
            all_products.extend(batch)
            url = None
            params = None
            for part in link_header.split(","):
                if 'rel="next"' in part:
                    url = part.split(";")[0].strip().strip("<>")
                    break

        log(f"Export — {len(all_products)} produit(s) après status={status}")

    print(f"  [INFO] {len(all_products)} produit(s) récupéré(s) (active + draft + archived)")
    return all_products


# ── Metafields produit (tous namespaces) ──────────────────────────────────────

EXPORT_NAMESPACES = {"custom", "global"}

def export_product_metafields(products, base_url, headers):
    """Retourne les metafields (custom + global) de chaque produit, avec namespace et type."""
    result = {}

    for product in tqdm(products, desc="Export metafields produit"):
        product_id = product["id"]
        url = f"{base_url}/products/{product_id}/metafields.json"
        data = shopify_get(url, headers)
        mfs = []
        for mf in data.get("metafields", []):
            if mf.get("namespace") in EXPORT_NAMESPACES:
                mfs.append({
                    "namespace": mf["namespace"],
                    "key": mf["key"],
                    "value": mf.get("value", ""),
                    "type": mf.get("type", ""),
                })
        if mfs:
            result[product_id] = mfs

    log(f"Export — metafields pour {len(result)} produit(s)")
    return result


# ── Résolution des file_reference GIDs → URLs ────────────────────────────────

def _collect_file_gids(metaobjects_by_type, product_metafields):
    """Collecte tous les GIDs file_reference uniques."""
    gids = set()
    for instances in metaobjects_by_type.values():
        for mo in instances:
            for field in mo["fields"]:
                if field["type"] == "file_reference" and field["value"]:
                    gids.add(field["value"])
    for mfs in product_metafields.values():
        for mf in mfs:
            if mf["type"] == "file_reference" and mf["value"]:
                gids.add(mf["value"])
    return list(gids)


def export_file_urls(base_url, headers, file_gids):
    """
    Résout les GIDs fichier en URLs téléchargeables.
    Retourne {gid: url}.
    """
    if not file_gids:
        return {}

    query = """
    query GetFileUrls($ids: [ID!]!) {
      nodes(ids: $ids) {
        ... on MediaImage {
          id
          image { url }
        }
        ... on GenericFile {
          id
          url
        }
        ... on Video {
          id
          sources { url }
        }
      }
    }
    """
    file_map = {}

    # L'API nodes() accepte max 250 IDs par appel
    for i in range(0, len(file_gids), 250):
        batch = file_gids[i:i + 250]
        data = graphql_request(base_url, headers, query, {"ids": batch})
        nodes = data.get("data", {}).get("nodes", [])
        for node in nodes:
            if not node:
                continue
            gid = node.get("id", "")
            url = None
            if "image" in node and node["image"]:
                url = node["image"].get("url")
            elif "url" in node:
                url = node["url"]
            elif "sources" in node and node["sources"]:
                url = node["sources"][0].get("url")
            if gid and url:
                file_map[gid] = url

    log(f"Export — {len(file_map)} URL(s) de fichier résolues sur {len(file_gids)} GID(s)")
    return file_map


# ── Export complet ────────────────────────────────────────────────────────────

def export_all(base_url, headers):
    """Export complet du store source. Retourne un dict avec toutes les données."""

    print("  [1/6] Metaobject definitions...")
    mo_defs = export_metaobject_definitions(base_url, headers)
    mo_types = [d["type"] for d in mo_defs if not d["type"].startswith("shopify--")]

    print("  [2/6] Metaobjects...")
    metaobjects = export_metaobjects(base_url, headers, mo_types)

    print("  [3/6] Metafield definitions...")
    mf_defs = export_metafield_definitions(base_url, headers)

    print("  [4/6] Produits...")
    products = export_products(base_url, headers)

    print("  [5/6] Metafields produit...")
    product_metafields = export_product_metafields(products, base_url, headers)

    print("  [6/6] Résolution des fichiers (images metaobjects)...")
    file_gids = _collect_file_gids(metaobjects, product_metafields)
    file_urls = export_file_urls(base_url, headers, file_gids)
    print(f"  [INFO] {len(file_urls)} fichier(s) résolu(s)")

    return {
        "metaobject_definitions": mo_defs,
        "metaobjects": metaobjects,
        "metafield_definitions": mf_defs,
        "products": products,
        "product_metafields": product_metafields,
        "file_urls": file_urls,
    }
