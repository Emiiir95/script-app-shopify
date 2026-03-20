from shopify.client import shopify_get, shopify_get_paginated, shopify_post, shopify_put, graphql_request
from utils.logger import log


def fetch_all_products(base_url, headers):
    products = []
    url = f"{base_url}/products.json"
    params = {"limit": 250, "fields": "id,handle,title"}

    while url:
        data, link_header = shopify_get_paginated(url, headers, params=params)
        batch = data.get("products", [])
        products.extend(batch)
        url = None
        params = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    log(f"{len(products)} produit(s) récupéré(s) depuis Shopify")
    print(f"[INFO] {len(products)} produit(s) récupéré(s).")
    return products


def fetch_all_products_full(base_url, headers):
    """Fetch tous les produits avec body_html et vendor (pour SEO Boost)."""
    products = []
    url = f"{base_url}/products.json"
    params = {"limit": 250, "fields": "id,handle,title,body_html,vendor,tags"}

    while url:
        data, link_header = shopify_get_paginated(url, headers, params=params)
        batch = data.get("products", [])
        products.extend(batch)
        url = None
        params = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    log(f"{len(products)} produit(s) récupéré(s) avec body_html depuis Shopify")
    print(f"[INFO] {len(products)} produit(s) récupéré(s).")
    return products


def fetch_all_products_with_variants(base_url, headers):
    """Fetch tous les produits avec leurs variantes (pour Normalisation)."""
    products = []
    url = f"{base_url}/products.json"
    params = {"limit": 250, "fields": "id,handle,title,status,variants"}

    while url:
        data, link_header = shopify_get_paginated(url, headers, params=params)
        batch = data.get("products", [])
        products.extend(batch)
        url = None
        params = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    log(f"{len(products)} produit(s) récupéré(s) avec variantes depuis Shopify")
    print(f"[INFO] {len(products)} produit(s) récupéré(s).")
    return products


def fetch_all_products_with_images(base_url, headers):
    """Fetch tous les produits avec body_html, vendor, tags ET images (pour Fiche Produit)."""
    products = []
    url = f"{base_url}/products.json"
    params = {"limit": 250, "fields": "id,handle,title,body_html,vendor,tags,images"}

    while url:
        data, link_header = shopify_get_paginated(url, headers, params=params)
        batch = data.get("products", [])
        products.extend(batch)
        url = None
        params = None
        for part in link_header.split(","):
            if 'rel="next"' in part:
                url = part.split(";")[0].strip().strip("<>")
                break

    log(f"{len(products)} produit(s) récupéré(s) avec images depuis Shopify")
    print(f"[INFO] {len(products)} produit(s) récupéré(s).")
    return products


def fetch_products_media_gids(base_url, headers):
    """
    Récupère les GIDs MediaImage de chaque produit via GraphQL.

    Les IDs images REST (product.images[].id) ≠ les IDs MediaImage GraphQL.
    Cette fonction retourne les vrais GIDs nécessaires pour les champs
    file_reference des metaobjects.

    Args:
        base_url : URL de base REST Shopify
        headers  : dict des headers HTTP Shopify

    Returns:
        dict : { product_handle: ["gid://shopify/MediaImage/...", ...] }
    """
    query = """
    query getProductsMedia($cursor: String) {
      products(first: 50, after: $cursor) {
        edges {
          node {
            handle
            media(first: 10) {
              edges {
                node {
                  ... on MediaImage {
                    id
                  }
                }
              }
            }
          }
          cursor
        }
        pageInfo { hasNextPage }
      }
    }
    """

    result = {}
    cursor = None

    while True:
        variables = {"cursor": cursor} if cursor else {}
        data = graphql_request(base_url, headers, query, variables)
        products_data = data.get("products", {})
        edges = products_data.get("edges", [])

        for edge in edges:
            node   = edge["node"]
            handle = node["handle"]
            gids   = [
                m["node"]["id"]
                for m in node.get("media", {}).get("edges", [])
                if m["node"].get("id")  # MediaImage nodes ont un id, les autres non
            ]
            result[handle] = gids
            cursor = edge.get("cursor")

        if not products_data.get("pageInfo", {}).get("hasNextPage"):
            break

    log(f"Media GIDs récupérés pour {len(result)} produit(s) via GraphQL")
    return result


def fetch_product_metafields(product_id, base_url, headers):
    url = f"{base_url}/products/{product_id}/metafields.json"
    data = shopify_get(url, headers)
    result = {}
    for mf in data.get("metafields", []):
        if mf.get("namespace") == "custom":
            result[mf["key"]] = mf.get("value", "")
    return result


def missing_review_slots(metafields):
    missing = []
    for i in range(1, 9):
        if not metafields.get(f"avis_client_{i}"):
            missing.append(i)
    return missing


def set_product_metafield(product_id, namespace, key, value, value_type, base_url, headers):
    mf_url = f"{base_url}/products/{product_id}/metafields.json"
    existing = shopify_get(mf_url, headers)
    mf_id = None
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
        shopify_post(f"{base_url}/products/{product_id}/metafields.json", headers, payload)
