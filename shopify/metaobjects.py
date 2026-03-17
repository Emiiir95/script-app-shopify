import requests
import time

from shopify.client import graphql_request
from utils.logger import log


def get_metaobject_definition_id(base_url, headers):
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
        for edge in data["data"]["metaobjectDefinitions"]["edges"]:
            if edge["node"]["type"] == "avis_client":
                return edge["node"]["id"]
    except Exception:
        pass
    return None


def create_metaobject_definition(base_url, headers):
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
            "type": "avis_client",
            "name": "Avis Client",
            "fieldDefinitions": [
                {"key": "photo_1",    "name": "Photo 1",    "type": "file_reference"},
                {"key": "photo_2",    "name": "Photo 2",    "type": "file_reference"},
                {"key": "note",       "name": "Note",       "type": "single_line_text_field"},
                {"key": "titre",      "name": "Titre",      "type": "single_line_text_field"},
                {"key": "texte",      "name": "Texte",      "type": "multi_line_text_field"},
                {"key": "nom_auteur", "name": "Nom auteur", "type": "single_line_text_field"},
            ],
            "capabilities": {
                "publishable": {"enabled": True}
            },
        }
    }
    data = graphql_request(base_url, headers, query, variables)
    result = data["data"]["metaobjectDefinitionCreate"]
    user_errors = result.get("userErrors", [])
    if user_errors:
        raise Exception(f"Erreur création metaobject definition : {user_errors}")
    mo_def = result["metaobjectDefinition"]
    log(f"Metaobject definition créée : {mo_def['type']} | id: {mo_def['id']}")
    return mo_def["id"]


def create_metafield_definition(base_url, headers, name, key, field_type, mo_def_id=None):
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

    data = graphql_request(base_url, headers, query, {"definition": definition})
    result = data["data"]["metafieldDefinitionCreate"]
    user_errors = result.get("userErrors", [])
    if user_errors:
        codes = [e.get("code", "") for e in user_errors]
        if "TAKEN" in codes or "taken" in str(user_errors).lower():
            log(f"Metafield definition déjà existante : custom.{key}")
            return
        raise Exception(f"Erreur création metafield {key} : {user_errors}")
    log(f"Metafield definition créée : custom.{key} ({field_type})")


def create_metaobject(review, base_url, headers, max_retries=5):
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
