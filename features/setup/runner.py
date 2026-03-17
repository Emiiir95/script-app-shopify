"""
runner.py — Feature Setup : création de toute la structure Shopify.

Crée (ou vérifie) l'ensemble des metaobjects et metafields définis dans
shopify_metafields_model.md, dans l'ordre imposé par les dépendances de référence.

Ordre de création :
  1. Metaobject definition  benefices_produit
  2. Metaobject definition  section_feature
  3. Metaobject definition  avis_client
  4. Metafields produit simples  (phrase, caracteristique, note_globale)
  5. Metafields produit références metaobjet
     (benefices, feature_1, feature_2, avis_client_1 … avis_client_8)

Usage :
  run(store_config, store_path)
"""

import time

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from shopify.metaobjects import (
    get_all_metaobject_definitions,
    create_metaobject_type,
    create_metafield_definition,
)
from utils.logger import log


# ── Schémas des metaobject definitions ────────────────────────────────────────

METAOBJECT_SCHEMAS = {
    "benefices_produit": {
        "name": "Bénéfices Produit",
        "fields": [
            {"key": "benefice_1", "name": "Bénéfice 1", "type": "single_line_text_field"},
            {"key": "benefice_2", "name": "Bénéfice 2", "type": "single_line_text_field"},
            {"key": "benefice_3", "name": "Bénéfice 3", "type": "single_line_text_field"},
        ],
    },
    "section_feature": {
        "name": "Section Feature",
        "fields": [
            {"key": "image",       "name": "Image",       "type": "file_reference"},
            {"key": "titre",       "name": "Titre",       "type": "single_line_text_field"},
            {"key": "description", "name": "Description", "type": "multi_line_text_field"},
        ],
    },
    "avis_client": {
        "name": "Avis Client",
        "fields": [
            {"key": "photo_1",    "name": "Photo 1",    "type": "file_reference"},
            {"key": "photo_2",    "name": "Photo 2",    "type": "file_reference"},
            {"key": "note",       "name": "Note",       "type": "single_line_text_field"},
            {"key": "titre",      "name": "Titre",      "type": "single_line_text_field"},
            {"key": "texte",      "name": "Texte",      "type": "multi_line_text_field"},
            {"key": "nom_auteur", "name": "Nom auteur", "type": "single_line_text_field"},
        ],
    },
}

# Ordre de création imposé par les dépendances (les références doivent exister avant)
METAOBJECT_CREATION_ORDER = ["benefices_produit", "section_feature", "avis_client"]


# ── Schémas des metafield definitions produit ─────────────────────────────────

# Champs simples (texte) — pas de référence metaobjet
SIMPLE_METAFIELDS = [
    {"key": "phrase",         "name": "Phrase d'accroche",       "type": "single_line_text_field"},
    {"key": "caracteristique","name": "Caractéristiques",        "type": "multi_line_text_field"},
    {"key": "note_globale",   "name": "Note globale du produit", "type": "single_line_text_field"},
]

# Champs référence metaobjet — résolus dynamiquement depuis les IDs créés
# Format : {"key": ..., "name": ..., "mo_type": ...}
METAOBJECT_REF_METAFIELDS = [
    {"key": "benefices",  "name": "Bénéfices",         "mo_type": "benefices_produit"},
    {"key": "feature_1",  "name": "Feature Section 1", "mo_type": "section_feature"},
    {"key": "feature_2",  "name": "Feature Section 2", "mo_type": "section_feature"},
    *[
        {"key": f"avis_client_{i}", "name": f"Avis Clients {i}", "mo_type": "avis_client"}
        for i in range(1, 9)
    ],
]


# ── Helpers d'affichage ───────────────────────────────────────────────────────

def _ok(label):
    print(f"  ✓ {label}")

def _fail(label, err):
    print(f"  ✗ {label} — {err}")


# ── Orchestration ─────────────────────────────────────────────────────────────

def _setup_metaobject_definitions(base_url, headers):
    """
    Vérifie et crée les 3 metaobject definitions dans l'ordre.
    Retourne un dict {type: id} avec tous les IDs (existants + créés).
    """
    print("\n[1/2] Metaobject definitions...")
    existing = get_all_metaobject_definitions(base_url, headers)
    log(f"Metaobject definitions existantes : {list(existing.keys())}")

    result_ids = dict(existing)

    for type_key in METAOBJECT_CREATION_ORDER:
        schema = METAOBJECT_SCHEMAS[type_key]
        if type_key in existing:
            _ok(f"'{type_key}' déjà existant")
            log(f"Metaobject definition déjà existante : {type_key}")
            continue

        print(f"  → Création '{type_key}'...")
        try:
            mo_id = create_metaobject_type(
                base_url, headers,
                type_key=type_key,
                name=schema["name"],
                field_defs=schema["fields"],
            )
            result_ids[type_key] = mo_id
            _ok(f"'{type_key}' créé")
        except Exception as e:
            _fail(type_key, e)
            log(f"Erreur création metaobject definition '{type_key}' : {e}", "error")
        time.sleep(0.3)

    return result_ids


def _setup_metafield_definitions(base_url, headers, mo_def_ids):
    """
    Crée les metafield definitions produit (simples puis références metaobjet).
    """
    print("\n[2/2] Metafield definitions produit...")

    # Champs simples
    for mf in SIMPLE_METAFIELDS:
        print(f"  → Champ simple '{mf['key']}'...")
        try:
            create_metafield_definition(
                base_url, headers,
                name=mf["name"],
                key=mf["key"],
                field_type=mf["type"],
            )
            _ok(mf["key"])
        except Exception as e:
            _fail(mf["key"], e)
            log(f"Erreur metafield '{mf['key']}' : {e}", "error")
        time.sleep(0.3)

    # Champs référence metaobjet
    for mf in METAOBJECT_REF_METAFIELDS:
        mo_type = mf["mo_type"]
        mo_id   = mo_def_ids.get(mo_type)

        if not mo_id:
            _fail(mf["key"], f"metaobject definition '{mo_type}' introuvable — ignoré")
            log(f"Metafield '{mf['key']}' ignoré : definition '{mo_type}' absente", "warning")
            continue

        print(f"  → Champ référence '{mf['key']}' → {mo_type}...")
        try:
            create_metafield_definition(
                base_url, headers,
                name=mf["name"],
                key=mf["key"],
                field_type="metaobject_reference",
                mo_def_id=mo_id,
            )
            _ok(mf["key"])
        except Exception as e:
            _fail(mf["key"], e)
            log(f"Erreur metafield '{mf['key']}' : {e}", "error")
        time.sleep(0.3)


def run(store_config, store_path):
    """
    Point d'entrée de la feature Setup.

    Args:
        store_config : dict avec clés name, store_url, access_token
        store_path   : chemin absolu vers le dossier de la boutique (non utilisé ici)
    """
    store_name = store_config.get("name", "boutique")

    print("=" * 60)
    print(f"  Setup — {store_name}")
    print("=" * 60)
    print("\nCette feature crée tous les metaobjects et metafields")
    print("définis dans shopify_metafields_model.md.")
    print("Les éléments déjà existants sont ignorés sans erreur.\n")

    answer = input("Lancer le setup ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    log(f"Début setup structure Shopify — boutique : {store_name}")

    base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(store_config["access_token"])

    # Étape 1 — Metaobject definitions
    mo_def_ids = _setup_metaobject_definitions(base_url, headers)

    # Étape 2 — Metafield definitions produit
    _setup_metafield_definitions(base_url, headers, mo_def_ids)

    print("\n" + "=" * 60)
    print("  Setup terminé.")
    print("  Tous les éléments existants ont été ignorés,")
    print("  les nouveaux ont été créés.")
    print("=" * 60)
    log("Setup structure Shopify terminé.")
