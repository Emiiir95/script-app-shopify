"""
metaobjects.py — Opérations CRUD sur les metaobjects et metaobject definitions Shopify.

Toutes les opérations passent par GraphQL (l'endpoint REST metaobjects est supprimé en 2026-01).

Fonctions publiques :
  get_all_metaobject_definitions(base_url, headers)       → dict {type: id}
  get_metaobject_definition_id(base_url, headers)         → str|None  (compat, avis_client uniquement)
  create_metaobject_type(base_url, headers, type_key, name, field_defs)  → str (id)
  create_metaobject_definition(base_url, headers)         → str (id)  (compat, avis_client)
  create_metafield_definition(base_url, headers, name, key, field_type, mo_def_id)
  create_metaobject(review, base_url, headers)            → str (GID)
"""

import requests
import time

from shopify.client import graphql_request
from utils.logger import log


# ── Capabilities partagées pour tous les metaobject definitions ──────────────

_CAPABILITIES = {
    "publishable":  {"enabled": True},
    "translatable": {"enabled": True},
}


# ── Lecture ───────────────────────────────────────────────────────────────────

def get_all_metaobject_definitions(base_url, headers):
    """
    Retourne un dict {type: id} pour toutes les metaobject definitions existantes.
    Ex: {"avis_client": "gid://shopify/MetaobjectDefinition/123", ...}
    """
    query = """
    {
      metaobjectDefinitions(first: 50) {
        edges {
          node { id type name }
        }
      }
    }
    """
    try:
        data = graphql_request(base_url, headers, query)
        return {
            edge["node"]["type"]: edge["node"]["id"]
            for edge in data["data"]["metaobjectDefinitions"]["edges"]
        }
    except Exception:
        return {}


def get_metaobject_definition_id(base_url, headers):
    """Retourne l'id de la definition 'avis_client', ou None. Conservé pour compatibilité."""
    return get_all_metaobject_definitions(base_url, headers).get("avis_client")


# ── Création de definitions ───────────────────────────────────────────────────

def create_metaobject_type(base_url, headers, type_key, name, field_defs):
    """
    Crée une metaobject definition générique.

    Args:
        type_key   : ex "avis_client"
        name       : ex "Avis Client"
        field_defs : liste de dicts {"key": ..., "name": ..., "type": ...}

    Returns:
        str : GID de la definition créée
    """
    query = """
    mutation CreateMetaobjectDefinition($definition: MetaobjectDefinitionCreateInput!) {
      metaobjectDefinitionCreate(definition: $definition) {
        metaobjectDefinition { id type name }
        userErrors { field message }
      }
    }
    """
    variables = {
        "definition": {
            "type":             type_key,
            "name":             name,
            "fieldDefinitions": field_defs,
            "capabilities":     _CAPABILITIES,
        }
    }
    data   = graphql_request(base_url, headers, query, variables)
    result = data["data"]["metaobjectDefinitionCreate"]

    user_errors = result.get("userErrors", [])
    if user_errors:
        raise Exception(f"Erreur création metaobject definition '{type_key}' : {user_errors}")

    mo_def = result["metaobjectDefinition"]
    log(f"Metaobject definition créée : {mo_def['type']} | id: {mo_def['id']}")
    return mo_def["id"]


def create_metaobject_definition(base_url, headers):
    """Crée la definition 'avis_client'. Conservé pour compatibilité avec les tests existants."""
    return create_metaobject_type(
        base_url, headers,
        type_key="avis_client",
        name="Avis Client",
        field_defs=[
            {"key": "photo_1",    "name": "Photo 1",    "type": "file_reference"},
            {"key": "photo_2",    "name": "Photo 2",    "type": "file_reference"},
            {"key": "note",       "name": "Note",       "type": "single_line_text_field"},
            {"key": "titre",      "name": "Titre",      "type": "single_line_text_field"},
            {"key": "texte",      "name": "Texte",      "type": "multi_line_text_field"},
            {"key": "nom_auteur", "name": "Nom auteur", "type": "single_line_text_field"},
        ],
    )


# ── Metafield definitions produit ─────────────────────────────────────────────

def create_metafield_definition(base_url, headers, name, key, field_type, mo_def_id=None):
    """
    Crée une metafield definition sur les produits (namespace 'custom').
    Ignore silencieusement si la clé existe déjà (code TAKEN).

    Args:
        mo_def_id : GID de la metaobject definition cible (requis si field_type == "metaobject_reference")
    """
    query = """
    mutation CreateMetafieldDefinition($definition: MetafieldDefinitionInput!) {
      metafieldDefinitionCreate(definition: $definition) {
        createdDefinition { id name namespace key }
        userErrors { field message code }
      }
    }
    """
    definition = {
        "name":      name,
        "namespace": "custom",
        "key":       key,
        "type":      field_type,
        "ownerType": "PRODUCT",
    }
    if mo_def_id:
        definition["validations"] = [
            {"name": "metaobject_definition_id", "value": mo_def_id}
        ]

    data   = graphql_request(base_url, headers, query, {"definition": definition})
    result = data["data"]["metafieldDefinitionCreate"]

    user_errors = result.get("userErrors", [])
    if user_errors:
        codes = [e.get("code", "") for e in user_errors]
        if "TAKEN" in codes or "taken" in str(user_errors).lower():
            log(f"Metafield definition déjà existante : custom.{key}")
            return
        raise Exception(f"Erreur création metafield '{key}' : {user_errors}")

    log(f"Metafield definition créée : custom.{key} ({field_type})")


# ── Création d'instances metaobject ───────────────────────────────────────────

def create_metaobject(review, base_url, headers, max_retries=5):
    """
    Crée un metaobject 'avis_client' avec les champs texte du review.
    Retourne le GID de l'objet créé.
    """
    store_url   = base_url.split("/admin/api/")[0]
    api_version = base_url.split("/admin/api/")[1]
    graphql_url = f"{store_url}/admin/api/{api_version}/graphql.json"

    query = """
    mutation CreateMetaobject($metaobject: MetaobjectCreateInput!) {
      metaobjectCreate(metaobject: $metaobject) {
        metaobject { id type }
        userErrors { field message }
      }
    }
    """
    variables = {
        "metaobject": {
            "type": "avis_client",
            "fields": [
                {"key": "note",       "value": str(review.get("note", 5))},
                {"key": "titre",      "value": review.get("titre", "")},
                {"key": "texte",      "value": review.get("texte", "")},
                {"key": "nom_auteur", "value": review.get("nom_auteur", "")},
            ],
            "capabilities": {
                "publishable": {"status": "ACTIVE"}
            },
        }
    }

    for attempt in range(max_retries):
        try:
            resp = requests.post(
                graphql_url,
                headers=headers,
                json={"query": query, "variables": variables},
                timeout=30,
            )
            if resp.status_code == 429:
                wait = int(float(resp.headers.get("Retry-After", 2)))
                log(f"Rate limit GraphQL — attente {wait}s (tentative {attempt+1})", "warning", also_print=True)
                time.sleep(wait)
                continue
            resp.raise_for_status()
            data = resp.json()

            if data.get("errors"):
                raise Exception(f"GraphQL errors : {data['errors']}")

            user_errors = data.get("data", {}).get("metaobjectCreate", {}).get("userErrors", [])
            if user_errors:
                raise Exception(f"userErrors : {user_errors}")

            return data["data"]["metaobjectCreate"]["metaobject"]["id"]

        except requests.exceptions.RequestException:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
                continue
            raise

    raise Exception("Impossible de créer le metaobject après plusieurs tentatives.")
