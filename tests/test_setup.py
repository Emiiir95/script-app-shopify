"""
Tests unitaires — features/setup/runner.py

Couvre : _setup_metaobject_definitions, _setup_metafield_definitions, run
"""
import unittest
from unittest.mock import patch, MagicMock, call

from features.setup.runner import (
    _setup_metaobject_definitions,
    _setup_metafield_definitions,
    METAOBJECT_CREATION_ORDER,
    SIMPLE_METAFIELDS,
    METAOBJECT_REF_METAFIELDS,
)

BASE_URL = "https://mystore.myshopify.com/admin/api/2026-01"
HEADERS  = {"X-Shopify-Access-Token": "test", "Content-Type": "application/json"}


class TestSetupMetaobjectDefinitions(unittest.TestCase):

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metaobject_type")
    @patch("features.setup.runner.get_all_metaobject_definitions")
    def test_creates_all_when_none_exist(self, mock_get_all, mock_create, mock_sleep):
        mock_get_all.return_value = {}
        mock_create.side_effect = lambda base_url, headers, type_key, name, field_defs: f"gid://{type_key}"

        result = _setup_metaobject_definitions(BASE_URL, HEADERS)

        self.assertEqual(mock_create.call_count, 3)
        for type_key in METAOBJECT_CREATION_ORDER:
            self.assertIn(type_key, result)

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metaobject_type")
    @patch("features.setup.runner.get_all_metaobject_definitions")
    def test_skips_existing_definitions(self, mock_get_all, mock_create, mock_sleep):
        mock_get_all.return_value = {
            "benefices_produit": "gid://bp/1",
            "section_feature":   "gid://sf/1",
            "avis_client":       "gid://ac/1",
        }

        result = _setup_metaobject_definitions(BASE_URL, HEADERS)

        mock_create.assert_not_called()
        self.assertEqual(result["avis_client"], "gid://ac/1")

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metaobject_type")
    @patch("features.setup.runner.get_all_metaobject_definitions")
    def test_creates_only_missing_definitions(self, mock_get_all, mock_create, mock_sleep):
        mock_get_all.return_value = {"benefices_produit": "gid://bp/1"}
        mock_create.side_effect = lambda base_url, headers, type_key, name, field_defs: f"gid://{type_key}"

        result = _setup_metaobject_definitions(BASE_URL, HEADERS)

        self.assertEqual(mock_create.call_count, 2)
        self.assertIn("section_feature", result)
        self.assertIn("avis_client", result)

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metaobject_type")
    @patch("features.setup.runner.get_all_metaobject_definitions")
    def test_error_on_creation_does_not_raise(self, mock_get_all, mock_create, mock_sleep):
        mock_get_all.return_value = {}
        mock_create.side_effect = Exception("API error")

        # Ne doit pas lever d'exception
        result = _setup_metaobject_definitions(BASE_URL, HEADERS)
        self.assertIsInstance(result, dict)

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metaobject_type")
    @patch("features.setup.runner.get_all_metaobject_definitions")
    def test_respects_creation_order(self, mock_get_all, mock_create, mock_sleep):
        mock_get_all.return_value = {}
        created_order = []
        def track_order(base_url, headers, type_key, name, field_defs):
            created_order.append(type_key)
            return f"gid://{type_key}"
        mock_create.side_effect = track_order

        _setup_metaobject_definitions(BASE_URL, HEADERS)

        self.assertEqual(created_order, METAOBJECT_CREATION_ORDER)


class TestSetupMetafieldDefinitions(unittest.TestCase):

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metafield_definition")
    def test_creates_all_simple_metafields(self, mock_create, mock_sleep):
        mo_def_ids = {
            "benefices_produit": "gid://bp/1",
            "section_feature":   "gid://sf/1",
            "avis_client":       "gid://ac/1",
        }

        _setup_metafield_definitions(BASE_URL, HEADERS, mo_def_ids)

        simple_keys_created = [
            c.kwargs.get("key") or c.args[3]
            for c in mock_create.call_args_list
        ]
        for mf in SIMPLE_METAFIELDS:
            self.assertIn(mf["key"], simple_keys_created)

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metafield_definition")
    def test_creates_all_reference_metafields(self, mock_create, mock_sleep):
        mo_def_ids = {
            "benefices_produit": "gid://bp/1",
            "section_feature":   "gid://sf/1",
            "avis_client":       "gid://ac/1",
        }

        _setup_metafield_definitions(BASE_URL, HEADERS, mo_def_ids)

        ref_keys_created = [
            c.kwargs.get("key") or c.args[3]
            for c in mock_create.call_args_list
        ]
        for mf in METAOBJECT_REF_METAFIELDS:
            self.assertIn(mf["key"], ref_keys_created)

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metafield_definition")
    def test_skips_ref_metafield_when_mo_def_missing(self, mock_create, mock_sleep):
        # Aucun metaobject def disponible
        _setup_metafield_definitions(BASE_URL, HEADERS, {})

        # Seuls les champs simples doivent avoir été créés
        self.assertEqual(mock_create.call_count, len(SIMPLE_METAFIELDS))

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metafield_definition")
    def test_error_on_metafield_creation_does_not_raise(self, mock_create, mock_sleep):
        mock_create.side_effect = Exception("API error")
        mo_def_ids = {"benefices_produit": "gid://1", "section_feature": "gid://2", "avis_client": "gid://3"}

        # Ne doit pas lever d'exception
        _setup_metafield_definitions(BASE_URL, HEADERS, mo_def_ids)

    @patch("features.setup.runner.time.sleep")
    @patch("features.setup.runner.create_metafield_definition")
    def test_avis_client_fields_use_correct_mo_def_id(self, mock_create, mock_sleep):
        mo_def_ids = {
            "benefices_produit": "gid://bp/1",
            "section_feature":   "gid://sf/1",
            "avis_client":       "gid://ac/99",
        }
        mock_create.return_value = None

        _setup_metafield_definitions(BASE_URL, HEADERS, mo_def_ids)

        # Vérifie que les appels pour avis_client_1..8 utilisent le bon mo_def_id
        for c in mock_create.call_args_list:
            key = c.kwargs.get("key") or c.args[3]
            if key.startswith("avis_client_"):
                mo_def_id = c.kwargs.get("mo_def_id") or (c.args[5] if len(c.args) > 5 else None)
                self.assertEqual(mo_def_id, "gid://ac/99")


class TestSetupSchemas(unittest.TestCase):
    """Vérifie la cohérence des schémas déclarés dans runner.py."""

    def test_all_three_metaobject_types_declared(self):
        self.assertIn("benefices_produit", METAOBJECT_CREATION_ORDER)
        self.assertIn("section_feature",   METAOBJECT_CREATION_ORDER)
        self.assertIn("avis_client",       METAOBJECT_CREATION_ORDER)

    def test_eight_avis_client_ref_metafields(self):
        avis_fields = [mf for mf in METAOBJECT_REF_METAFIELDS if mf["key"].startswith("avis_client_")]
        self.assertEqual(len(avis_fields), 8)
        for i in range(1, 9):
            keys = [mf["key"] for mf in avis_fields]
            self.assertIn(f"avis_client_{i}", keys)

    def test_three_simple_metafields(self):
        keys = [mf["key"] for mf in SIMPLE_METAFIELDS]
        self.assertIn("phrase",          keys)
        self.assertIn("caracteristique", keys)
        self.assertIn("note_globale",    keys)


if __name__ == "__main__":
    unittest.main()
