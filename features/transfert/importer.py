"""
importer.py — Injection complète vers un store Shopify destination.

Ordre d'import (chaîne de dépendances) :
  1. Metaobject definitions  → remap {source_def_id: dest_def_id}
  2. Metafield definitions   → remap des mo_def_id dans les validations
  3. Fichiers (images)       → upload via fileCreate, remap {source_gid: dest_gid}
  4. Metaobjects             → remap GID fichiers + remap {source_gid: dest_gid}
  5. Produits                → remap {source_product_id: dest_product_id}
  6. Metafields produit      → remap GID metaobject_reference + file_reference
"""

import time

from tqdm import tqdm

from shopify.client import shopify_post, shopify_put, graphql_request
from shopify.metaobjects import (
    get_all_metaobject_definitions,
    create_metaobject_type,
    create_metafield_definition,
    create_metaobject_generic,
)
from shopify.products import set_product_metafield
from utils.logger import log


# ── 1. Metaobject Definitions ─────────────────────────────────────────────────

def import_metaobject_definitions(mo_defs, dest_base_url, dest_headers):
    """
    Crée les metaobject definitions manquantes sur la destination.
    Retourne le mapping {source_def_id: dest_def_id}.
    """
    existing = get_all_metaobject_definitions(dest_base_url, dest_headers)
    mo_def_remap = {}

    for mo_def in mo_defs:
        type_key = mo_def["type"]

        if type_key.startswith("shopify--"):
            print(f"  ⊘ '{type_key}' — type réservé Shopify, ignoré")
            continue

        if type_key in existing:
            mo_def_remap[mo_def["source_id"]] = existing[type_key]
            print(f"  ✓ '{type_key}' déjà existante")
            continue

        field_defs = [
            {"key": f["key"], "name": f["name"], "type": f["type"]}
            for f in mo_def["fieldDefinitions"]
        ]
        new_id = create_metaobject_type(
            dest_base_url, dest_headers,
            type_key=type_key, name=mo_def["name"], field_defs=field_defs,
        )
        mo_def_remap[mo_def["source_id"]] = new_id
        print(f"  → '{type_key}' créée")

    return mo_def_remap


# ── 2. Metafield Definitions ─────────────────────────────────────────────────

def import_metafield_definitions(mf_defs, mo_def_remap, dest_base_url, dest_headers):
    """Crée les metafield definitions (product/custom) sur la destination."""
    for mf_def in mf_defs:
        mo_def_id = None

        if mf_def["type"] == "metaobject_reference":
            for v in mf_def.get("validations", []):
                if v["name"] == "metaobject_definition_id":
                    source_mo_def_id = v["value"]
                    mo_def_id = mo_def_remap.get(source_mo_def_id)
                    break

        create_metafield_definition(
            dest_base_url, dest_headers,
            name=mf_def["name"],
            key=mf_def["key"],
            field_type=mf_def["type"],
            mo_def_id=mo_def_id,
        )

    print(f"  ✓ {len(mf_defs)} metafield definition(s) traitée(s)")


# ── 3. Fichiers (images) ─────────────────────────────────────────────────────

def import_files(file_urls, dest_base_url, dest_headers):
    """
    Crée les fichiers sur la destination via fileCreate (Shopify re-télécharge depuis l'URL).
    Retourne le mapping {source_file_gid: dest_file_gid}.
    """
    if not file_urls:
        print("  ✓ Aucun fichier à transférer")
        return {}

    file_remap = {}
    fail_count = 0

    mutation = """
    mutation fileCreate($files: [FileCreateInput!]!) {
      fileCreate(files: $files) {
        files {
          id
          alt
        }
        userErrors {
          field
          message
        }
      }
    }
    """

    items = list(file_urls.items())

    for source_gid, url in tqdm(items, desc="Import fichiers"):
        variables = {
            "files": [{
                "originalSource": url,
                "contentType": "IMAGE",
            }]
        }

        try:
            data = graphql_request(dest_base_url, dest_headers, mutation, variables)
            result = data.get("data", {}).get("fileCreate", {})
            errors = result.get("userErrors", [])

            if errors:
                log(f"Erreur fileCreate pour {source_gid}: {errors}", "error")
                fail_count += 1
                continue

            files = result.get("files", [])
            if files:
                new_gid = files[0]["id"]
                file_remap[source_gid] = new_gid
        except Exception as e:
            log(f"Erreur upload fichier {source_gid}: {e}", "error")
            fail_count += 1

        time.sleep(0.3)

    if fail_count:
        print(f"  ⚠ {fail_count} fichier(s) en erreur")
    print(f"  ✓ {len(file_remap)} fichier(s) créé(s)")

    return file_remap


# ── 4. Metaobjects ───────────────────────────────────────────────────────────

def import_metaobjects(metaobjects_by_type, file_remap, dest_base_url, dest_headers):
    """
    Crée tous les metaobjects sur la destination.
    Les champs file_reference sont remappés via file_remap.
    Retourne le mapping {source_gid: dest_gid}.
    """
    metaobject_remap = {}
    skipped_files = 0

    total = sum(len(v) for v in metaobjects_by_type.values())

    with tqdm(total=total, desc="Import metaobjects") as pbar:
        for type_key, instances in metaobjects_by_type.items():
            if type_key.startswith("shopify--"):
                pbar.update(len(instances))
                continue
            for mo in instances:
                fields = []
                for field in mo["fields"]:
                    if not field["value"]:
                        continue

                    value = field["value"]

                    # Remap les file_reference vers le nouveau GID
                    if field["type"] == "file_reference":
                        new_gid = file_remap.get(value)
                        if not new_gid:
                            skipped_files += 1
                            continue
                        value = new_gid

                    fields.append({"key": field["key"], "value": value})

                try:
                    new_gid = create_metaobject_generic(
                        type_key, fields, dest_base_url, dest_headers,
                    )
                    metaobject_remap[mo["source_id"]] = new_gid
                except Exception as e:
                    log(f"Erreur création metaobject {type_key}: {e}", "error", also_print=True)

                pbar.update(1)
                time.sleep(0.3)

    if skipped_files:
        print(f"  ⚠ {skipped_files} champ(s) file_reference sans remap (fichier non transféré)")

    return metaobject_remap


# ── 5. Produits ───────────────────────────────────────────────────────────────

def _build_product_payload(product):
    """Construit le payload REST pour créer un produit sur la destination."""
    payload = {
        "title": product.get("title", ""),
        "body_html": product.get("body_html", ""),
        "vendor": product.get("vendor", ""),
        "product_type": product.get("product_type", ""),
        "tags": product.get("tags", ""),
        "status": product.get("status", "draft"),
        "handle": product.get("handle", ""),
    }

    options = product.get("options", [])
    if options:
        payload["options"] = [
            {"name": opt["name"], "values": opt.get("values", [])}
            for opt in options
        ]

    variants = product.get("variants", [])
    if variants:
        payload["variants"] = []
        for v in variants:
            variant = {
                "price": v.get("price"),
                "compare_at_price": v.get("compare_at_price"),
                "sku": v.get("sku", ""),
                "barcode": v.get("barcode", ""),
                "option1": v.get("option1"),
                "option2": v.get("option2"),
                "option3": v.get("option3"),
                "inventory_management": v.get("inventory_management"),
                "inventory_policy": v.get("inventory_policy", "deny"),
                "weight": v.get("weight"),
                "weight_unit": v.get("weight_unit"),
                "taxable": v.get("taxable", True),
                "requires_shipping": v.get("requires_shipping", True),
                "fulfillment_service": v.get("fulfillment_service", "manual"),
            }
            payload["variants"].append(variant)

    images = product.get("images", [])
    if images:
        payload["images"] = [
            {
                "src": img.get("src", ""),
                "alt": img.get("alt", ""),
                "position": img.get("position"),
            }
            for img in images
            if img.get("src")
        ]

    return payload


def _link_variant_images(source_product, dest_product, dest_base_url, dest_headers):
    """
    Associe les images aux variantes sur la destination.
    Mappe via la position de l'image source → image destination.
    """
    source_images = source_product.get("images", [])
    dest_images = dest_product.get("images", [])
    source_variants = source_product.get("variants", [])
    dest_variants = dest_product.get("variants", [])

    if not source_images or not dest_images or not source_variants:
        return

    # Mapping source_image_id → position
    source_id_to_pos = {img["id"]: img.get("position", i + 1) for i, img in enumerate(source_images)}
    # Mapping position → dest_image_id
    pos_to_dest_id = {img.get("position", i + 1): img["id"] for i, img in enumerate(dest_images)}

    for i, src_variant in enumerate(source_variants):
        src_image_id = src_variant.get("image_id")
        if not src_image_id:
            continue
        if i >= len(dest_variants):
            break

        position = source_id_to_pos.get(src_image_id)
        if not position:
            continue
        dest_image_id = pos_to_dest_id.get(position)
        if not dest_image_id:
            continue

        dest_variant_id = dest_variants[i]["id"]
        dest_product_id = dest_product["id"]

        try:
            shopify_put(
                f"{dest_base_url}/variants/{dest_variant_id}.json",
                dest_headers,
                {"variant": {"id": dest_variant_id, "image_id": dest_image_id}},
            )
        except Exception as e:
            log(f"Erreur lien image variante {dest_variant_id}: {e}", "error")


def import_products(products, dest_base_url, dest_headers):
    """
    Crée tous les produits sur la destination avec images variantes.
    Retourne le mapping {source_product_id: dest_product_id}.
    """
    product_remap = {}
    fail_count = 0

    for product in tqdm(products, desc="Import produits"):
        try:
            payload = {"product": _build_product_payload(product)}
            url = f"{dest_base_url}/products.json"
            result = shopify_post(url, dest_headers, payload)
            dest_product = result["product"]
            new_id = dest_product["id"]
            product_remap[product["id"]] = new_id
            log(f"Produit créé — {product.get('handle', '')} → ID {new_id}")

            # Associer les images aux variantes
            _link_variant_images(product, dest_product, dest_base_url, dest_headers)

        except Exception as e:
            fail_count += 1
            log(f"Erreur création produit {product.get('handle', '')}: {e}", "error", also_print=True)

        time.sleep(0.5)

    if fail_count:
        print(f"  ⚠ {fail_count} produit(s) en erreur")

    return product_remap


# ── 6. Metafields produit ─────────────────────────────────────────────────────

def import_product_metafields(product_metafields, product_remap, metaobject_remap,
                              file_remap, dest_base_url, dest_headers):
    """
    Injecte les metafields sur chaque produit destination.
    Utilise le namespace d'origine (custom, global, etc.).
    Les valeurs metaobject_reference et file_reference sont remappées.
    """
    total = sum(len(mfs) for mfs in product_metafields.values())
    skipped = 0

    with tqdm(total=total, desc="Import metafields produit") as pbar:
        for source_pid, metafields in product_metafields.items():
            dest_pid = product_remap.get(source_pid)
            if not dest_pid:
                log(f"Product {source_pid} non trouvé dans le remap — skip metafields", "warning")
                pbar.update(len(metafields))
                continue

            for mf in metafields:
                value = mf["value"]
                mf_type = mf["type"]
                namespace = mf.get("namespace", "custom")

                # Remap GID pour les metaobject_reference
                if mf_type == "metaobject_reference" and value:
                    new_gid = metaobject_remap.get(value)
                    if not new_gid:
                        log(f"GID metaobject non remappé: {value} (product {source_pid}, key {mf['key']})", "warning")
                        skipped += 1
                        pbar.update(1)
                        continue
                    value = new_gid

                # Remap GID pour les file_reference
                if mf_type == "file_reference" and value:
                    new_gid = file_remap.get(value)
                    if not new_gid:
                        log(f"GID fichier non remappé: {value} (product {source_pid}, key {mf['key']})", "warning")
                        skipped += 1
                        pbar.update(1)
                        continue
                    value = new_gid

                if not value:
                    pbar.update(1)
                    continue

                try:
                    set_product_metafield(
                        dest_pid, namespace, mf["key"],
                        value, mf_type,
                        dest_base_url, dest_headers,
                    )
                except Exception as e:
                    log(f"Erreur metafield {namespace}.{mf['key']} sur product {dest_pid}: {e}", "error")

                pbar.update(1)
                time.sleep(0.3)

    if skipped:
        print(f"  ⚠ {skipped} metafield(s) ignoré(s) (GID non remappé)")


# ── Import complet ────────────────────────────────────────────────────────────

def import_all(export_data, dest_base_url, dest_headers):
    """
    Import complet vers la destination.
    Retourne les tables de remap pour le résumé final.
    """
    print("\n  [1/6] Metaobject definitions...")
    mo_def_remap = import_metaobject_definitions(
        export_data["metaobject_definitions"], dest_base_url, dest_headers)

    print("\n  [2/6] Metafield definitions...")
    import_metafield_definitions(
        export_data["metafield_definitions"], mo_def_remap, dest_base_url, dest_headers)

    print("\n  [3/6] Fichiers (images)...")
    file_remap = import_files(
        export_data.get("file_urls", {}), dest_base_url, dest_headers)

    print("\n  [4/6] Metaobjects...")
    metaobject_remap = import_metaobjects(
        export_data["metaobjects"], file_remap, dest_base_url, dest_headers)

    print("\n  [5/6] Produits...")
    product_remap = import_products(
        export_data["products"], dest_base_url, dest_headers)

    print("\n  [6/6] Metafields produit...")
    import_product_metafields(
        export_data["product_metafields"], product_remap, metaobject_remap,
        file_remap, dest_base_url, dest_headers)

    return {
        "mo_def_remap": mo_def_remap,
        "metaobject_remap": metaobject_remap,
        "product_remap": product_remap,
        "file_remap": file_remap,
    }
