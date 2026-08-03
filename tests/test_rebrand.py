"""
Tests unitaires — features/rebrand/injector.py

Couvre : apply_replacements, compute_product_changes, fetch_all_products_seo,
         update_product, generate_report
"""
import csv
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from features.rebrand.injector import (
    apply_replacements,
    compute_product_changes,
    fetch_all_products_seo,
    update_product,
    generate_report,
)


REPLACEMENTS = [
    {"from": "le-perchoir-du-chat.com", "to": "perchoirduchat.com"},
    {"from": "Le Perchoir Du Chat",     "to": "Perchoir Du Chat"},
]


class TestApplyReplacements(unittest.TestCase):
    def test_replaces_single_occurrence(self):
        out = apply_replacements("Visitez Le Perchoir Du Chat", REPLACEMENTS)
        self.assertEqual(out, "Visitez Perchoir Du Chat")

    def test_replaces_all_occurrences(self):
        text = "Le Perchoir Du Chat et encore Le Perchoir Du Chat"
        out  = apply_replacements(text, REPLACEMENTS)
        self.assertEqual(out, "Perchoir Du Chat et encore Perchoir Du Chat")

    def test_applies_multiple_rules(self):
        text = "Voir le-perchoir-du-chat.com — Le Perchoir Du Chat"
        out  = apply_replacements(text, REPLACEMENTS)
        self.assertEqual(out, "Voir perchoirduchat.com — Perchoir Du Chat")

    def test_no_match_returns_unchanged(self):
        out = apply_replacements("Aucune marque ici", REPLACEMENTS)
        self.assertEqual(out, "Aucune marque ici")

    def test_empty_text_returns_as_is(self):
        self.assertEqual(apply_replacements("", REPLACEMENTS), "")
        self.assertIsNone(apply_replacements(None, REPLACEMENTS))

    def test_ignores_rule_with_empty_from(self):
        out = apply_replacements("texte", [{"from": "", "to": "X"}])
        self.assertEqual(out, "texte")

    def test_missing_to_replaces_with_empty(self):
        out = apply_replacements("supprime moi ça", [{"from": " ça", "to": ""}])
        self.assertEqual(out, "supprime moi")


class TestComputeProductChanges(unittest.TestCase):
    def test_detects_changes_on_all_fields(self):
        product = {
            "description_html": "<p>Le Perchoir Du Chat</p>",
            "seo_title":        "Le Perchoir Du Chat | Boutique",
            "seo_description":  "Découvrez le-perchoir-du-chat.com",
        }
        result = compute_product_changes(product, REPLACEMENTS)

        self.assertTrue(result["changed"])
        self.assertEqual(set(result["fields"]), {"description_html", "seo_title", "seo_description"})

    def test_field_tuple_is_old_new(self):
        product = {"description_html": "Le Perchoir Du Chat", "seo_title": "", "seo_description": ""}
        result  = compute_product_changes(product, REPLACEMENTS)

        old, new = result["fields"]["description_html"]
        self.assertEqual(old, "Le Perchoir Du Chat")
        self.assertEqual(new, "Perchoir Du Chat")

    def test_no_change_returns_changed_false(self):
        product = {"description_html": "rien", "seo_title": "rien", "seo_description": "rien"}
        result  = compute_product_changes(product, REPLACEMENTS)

        self.assertFalse(result["changed"])
        self.assertEqual(result["fields"], {})

    def test_only_modified_fields_are_included(self):
        product = {
            "description_html": "Le Perchoir Du Chat",
            "seo_title":        "inchangé",
            "seo_description":  "inchangé",
        }
        result = compute_product_changes(product, REPLACEMENTS)

        self.assertEqual(list(result["fields"]), ["description_html"])

    def test_missing_fields_default_to_empty(self):
        result = compute_product_changes({}, REPLACEMENTS)
        self.assertFalse(result["changed"])


class TestFetchAllProductsSeo(unittest.TestCase):
    @patch("features.rebrand.injector.graphql_request")
    def test_single_page(self, mock_gql):
        mock_gql.return_value = {
            "data": {"products": {
                "nodes": [
                    {"id": "gid://1", "handle": "a", "title": "A",
                     "descriptionHtml": "<p>A</p>", "seo": {"title": "TA", "description": "DA"}},
                ],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}
        }
        products = fetch_all_products_seo("http://base", {})

        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["gid"], "gid://1")
        self.assertEqual(products[0]["description_html"], "<p>A</p>")
        self.assertEqual(products[0]["seo_title"], "TA")
        self.assertEqual(products[0]["seo_description"], "DA")

    @patch("features.rebrand.injector.graphql_request")
    def test_pagination_follows_cursor(self, mock_gql):
        mock_gql.side_effect = [
            {"data": {"products": {
                "nodes": [{"id": "gid://1", "handle": "a", "title": "A",
                           "descriptionHtml": "", "seo": {"title": "", "description": ""}}],
                "pageInfo": {"hasNextPage": True, "endCursor": "CURSOR1"},
            }}},
            {"data": {"products": {
                "nodes": [{"id": "gid://2", "handle": "b", "title": "B",
                           "descriptionHtml": "", "seo": {"title": "", "description": ""}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}},
        ]
        products = fetch_all_products_seo("http://base", {})

        self.assertEqual(len(products), 2)
        self.assertEqual(mock_gql.call_count, 2)
        # 2ème appel doit passer le cursor de la 1ère page
        self.assertEqual(mock_gql.call_args_list[1][0][3]["cursor"], "CURSOR1")

    @patch("features.rebrand.injector.graphql_request")
    def test_null_seo_fields_become_empty_string(self, mock_gql):
        mock_gql.return_value = {
            "data": {"products": {
                "nodes": [{"id": "gid://1", "handle": "a", "title": "A",
                           "descriptionHtml": None, "seo": {"title": None, "description": None}}],
                "pageInfo": {"hasNextPage": False, "endCursor": None},
            }}
        }
        products = fetch_all_products_seo("http://base", {})

        self.assertEqual(products[0]["description_html"], "")
        self.assertEqual(products[0]["seo_title"], "")
        self.assertEqual(products[0]["seo_description"], "")


class TestUpdateProduct(unittest.TestCase):
    PRODUCT = {"gid": "gid://shopify/Product/1", "handle": "prod-a", "title": "A"}

    @patch("features.rebrand.injector.graphql_request")
    def test_builds_description_payload(self, mock_gql):
        mock_gql.return_value = {"data": {"productUpdate": {"userErrors": []}}}
        changes = {"fields": {"description_html": ("old", "new")}}

        update_product(self.PRODUCT, changes, "http://base", {})

        payload = mock_gql.call_args[0][3]["input"]
        self.assertEqual(payload["id"], "gid://shopify/Product/1")
        self.assertEqual(payload["descriptionHtml"], "new")
        self.assertNotIn("seo", payload)

    @patch("features.rebrand.injector.graphql_request")
    def test_builds_seo_payload(self, mock_gql):
        mock_gql.return_value = {"data": {"productUpdate": {"userErrors": []}}}
        changes = {"fields": {
            "seo_title":       ("oldT", "newT"),
            "seo_description": ("oldD", "newD"),
        }}
        update_product(self.PRODUCT, changes, "http://base", {})

        payload = mock_gql.call_args[0][3]["input"]
        self.assertEqual(payload["seo"]["title"], "newT")
        self.assertEqual(payload["seo"]["description"], "newD")
        self.assertNotIn("descriptionHtml", payload)

    @patch("features.rebrand.injector.graphql_request")
    def test_raises_on_user_errors(self, mock_gql):
        mock_gql.return_value = {"data": {"productUpdate": {
            "userErrors": [{"field": "seo", "message": "invalid"}]
        }}}
        changes = {"fields": {"seo_title": ("a", "b")}}

        with self.assertRaises(Exception):
            update_product(self.PRODUCT, changes, "http://base", {})


class TestGenerateReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_creates_csv_in_rapports_folder(self):
        rows = [{"handle": "a", "titre": "A", "champ": "Meta Title", "statut": "OK", "erreur": ""}]
        path = generate_report(rows, self.tmpdir)

        self.assertTrue(os.path.exists(path))
        self.assertIn("rapports", path)

    def test_csv_content_matches_rows(self):
        rows = [
            {"handle": "a", "titre": "A", "champ": "Description HTML", "statut": "OK",     "erreur": ""},
            {"handle": "b", "titre": "B", "champ": "Meta Title",       "statut": "ERREUR", "erreur": "boom"},
        ]
        path = generate_report(rows, self.tmpdir)

        with open(path, encoding="utf-8-sig") as f:
            read = list(csv.DictReader(f))

        self.assertEqual(len(read), 2)
        self.assertEqual(read[0]["handle"], "a")
        self.assertEqual(read[1]["statut"], "ERREUR")
        self.assertEqual(read[1]["erreur"], "boom")


if __name__ == "__main__":
    unittest.main()
