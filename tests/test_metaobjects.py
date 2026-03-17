"""
Tests unitaires — shopify/metaobjects.py

Couvre : get_metaobject_definition_id, create_metaobject_definition,
         create_metafield_definition, create_metaobject
"""
import unittest
from unittest.mock import patch, MagicMock

from shopify.metaobjects import (
    create_metafield_definition,
    create_metaobject,
    create_metaobject_definition,
    get_metaobject_definition_id,
)

BASE_URL = "https://mystore.myshopify.com/admin/api/2026-01"
HEADERS  = {"X-Shopify-Access-Token": "test", "Content-Type": "application/json"}


class TestGetMetaobjectDefinitionId(unittest.TestCase):
    @patch("shopify.metaobjects.graphql_request")
    def test_found_returns_id(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "metaobjectDefinitions": {
                    "edges": [
                        {"node": {"id": "gid://123", "type": "avis_client", "name": "Avis Client"}}
                    ]
                }
            }
        }
        result = get_metaobject_definition_id(BASE_URL, HEADERS)
        self.assertEqual(result, "gid://123")

    @patch("shopify.metaobjects.graphql_request")
    def test_not_found_returns_none(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "metaobjectDefinitions": {
                    "edges": [
                        {"node": {"id": "gid://456", "type": "other_type", "name": "Other"}}
                    ]
                }
            }
        }
        result = get_metaobject_definition_id(BASE_URL, HEADERS)
        self.assertIsNone(result)

    @patch("shopify.metaobjects.graphql_request")
    def test_empty_edges_returns_none(self, mock_gql):
        mock_gql.return_value = {
            "data": {"metaobjectDefinitions": {"edges": []}}
        }
        result = get_metaobject_definition_id(BASE_URL, HEADERS)
        self.assertIsNone(result)

    @patch("shopify.metaobjects.graphql_request")
    def test_exception_returns_none(self, mock_gql):
        mock_gql.side_effect = Exception("Network error")
        result = get_metaobject_definition_id(BASE_URL, HEADERS)
        self.assertIsNone(result)


class TestCreateMetaobjectDefinition(unittest.TestCase):
    @patch("shopify.metaobjects.graphql_request")
    def test_success_returns_id(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "metaobjectDefinitionCreate": {
                    "metaobjectDefinition": {"id": "gid://def/1", "type": "avis_client", "name": "Avis Client"},
                    "userErrors": [],
                }
            }
        }
        result = create_metaobject_definition(BASE_URL, HEADERS)
        self.assertEqual(result, "gid://def/1")

    @patch("shopify.metaobjects.graphql_request")
    def test_user_errors_raises(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "metaobjectDefinitionCreate": {
                    "metaobjectDefinition": None,
                    "userErrors": [{"field": "type", "message": "already exists"}],
                }
            }
        }
        with self.assertRaises(Exception) as ctx:
            create_metaobject_definition(BASE_URL, HEADERS)
        self.assertIn("Erreur création metaobject definition", str(ctx.exception))


class TestCreateMetafieldDefinition(unittest.TestCase):
    @patch("shopify.metaobjects.graphql_request")
    def test_success_does_not_raise(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "metafieldDefinitionCreate": {
                    "createdDefinition": {"id": "gid://1", "name": "Note", "namespace": "custom", "key": "note"},
                    "userErrors": [],
                }
            }
        }
        create_metafield_definition(BASE_URL, HEADERS, "Note", "note_globale", "single_line_text_field")

    @patch("shopify.metaobjects.graphql_request")
    def test_taken_error_is_silent(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "metafieldDefinitionCreate": {
                    "createdDefinition": None,
                    "userErrors": [{"field": "key", "message": "already taken", "code": "TAKEN"}],
                }
            }
        }
        # Ne doit pas lever d'exception
        create_metafield_definition(BASE_URL, HEADERS, "Note", "note_globale", "single_line_text_field")

    @patch("shopify.metaobjects.graphql_request")
    def test_other_error_raises(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "metafieldDefinitionCreate": {
                    "createdDefinition": None,
                    "userErrors": [{"field": "type", "message": "Invalid type", "code": "INVALID"}],
                }
            }
        }
        with self.assertRaises(Exception) as ctx:
            create_metafield_definition(BASE_URL, HEADERS, "Note", "note_globale", "bad_type")
        self.assertIn("Erreur création metafield", str(ctx.exception))

    @patch("shopify.metaobjects.graphql_request")
    def test_includes_validation_when_mo_def_id_provided(self, mock_gql):
        mock_gql.return_value = {
            "data": {
                "metafieldDefinitionCreate": {
                    "createdDefinition": {"id": "gid://1", "name": "Avis 1", "namespace": "custom", "key": "avis_clients_1"},
                    "userErrors": [],
                }
            }
        }
        create_metafield_definition(
            BASE_URL, HEADERS, "Avis 1", "avis_clients_1", "metaobject_reference", mo_def_id="gid://def/1"
        )
        variables = mock_gql.call_args[0][3]
        self.assertIn("validations", variables["definition"])


class TestCreateMetaobject(unittest.TestCase):
    REVIEW = {"note": "4.8", "titre": "Super produit", "texte": "Très content", "nom_auteur": "Jean D."}

    @patch("shopify.metaobjects.requests.post")
    def test_success_returns_gid(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "metaobjectCreate": {
                    "metaobject": {"id": "gid://shopify/Metaobject/1", "type": "avis_client"},
                    "userErrors": [],
                }
            }
        }
        mock_post.return_value = mock_resp

        gid = create_metaobject(self.REVIEW, BASE_URL, HEADERS)
        self.assertEqual(gid, "gid://shopify/Metaobject/1")

    @patch("shopify.metaobjects.requests.post")
    def test_user_errors_raises(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "metaobjectCreate": {
                    "metaobject": None,
                    "userErrors": [{"field": "type", "message": "Invalid type"}],
                }
            }
        }
        mock_post.return_value = mock_resp

        with self.assertRaises(Exception) as ctx:
            create_metaobject({}, BASE_URL, HEADERS)
        self.assertIn("userErrors", str(ctx.exception))

    @patch("shopify.metaobjects.requests.post")
    def test_graphql_errors_raises(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"errors": [{"message": "Syntax error"}]}
        mock_post.return_value = mock_resp

        with self.assertRaises(Exception) as ctx:
            create_metaobject(self.REVIEW, BASE_URL, HEADERS)
        self.assertIn("GraphQL errors", str(ctx.exception))

    @patch("shopify.metaobjects.time.sleep")
    @patch("shopify.metaobjects.requests.post")
    def test_rate_limit_retries_and_succeeds(self, mock_post, mock_sleep):
        rate_limited = MagicMock()
        rate_limited.status_code = 429
        rate_limited.headers = {"Retry-After": "2"}

        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {
            "data": {
                "metaobjectCreate": {
                    "metaobject": {"id": "gid://1", "type": "avis_client"},
                    "userErrors": [],
                }
            }
        }
        mock_post.side_effect = [rate_limited, success]

        gid = create_metaobject(self.REVIEW, BASE_URL, HEADERS)
        self.assertEqual(gid, "gid://1")
        mock_sleep.assert_called_with(2)

    @patch("shopify.metaobjects.time.sleep")
    @patch("shopify.metaobjects.requests.post")
    def test_network_error_retries(self, mock_post, mock_sleep):
        import requests as req
        success = MagicMock()
        success.status_code = 200
        success.json.return_value = {
            "data": {
                "metaobjectCreate": {
                    "metaobject": {"id": "gid://1", "type": "avis_client"},
                    "userErrors": [],
                }
            }
        }
        mock_post.side_effect = [req.exceptions.Timeout(), success]

        gid = create_metaobject(self.REVIEW, BASE_URL, HEADERS, max_retries=2)
        self.assertEqual(gid, "gid://1")

    @patch("shopify.metaobjects.requests.post")
    def test_payload_includes_all_review_fields(self, mock_post):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "data": {
                "metaobjectCreate": {
                    "metaobject": {"id": "gid://1", "type": "avis_client"},
                    "userErrors": [],
                }
            }
        }
        mock_post.return_value = mock_resp

        create_metaobject(self.REVIEW, BASE_URL, HEADERS)

        payload = mock_post.call_args[1]["json"]
        fields = {f["key"]: f["value"] for f in payload["variables"]["metaobject"]["fields"]}
        self.assertEqual(fields["note"], "4.8")
        self.assertEqual(fields["titre"], "Super produit")
        self.assertEqual(fields["nom_auteur"], "Jean D.")


if __name__ == "__main__":
    unittest.main()
