#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_politiques.py — Tests unitaires pour features/politiques/

Couvre :
  - processor : load_template, fill_placeholders, list_missing_templates
  - injector  : update_shopify_policies, fetch_page_by_handle,
                create_page, update_page, generate_injection_report
"""

import csv
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

from features.politiques.processor import (
    load_template,
    fill_placeholders,
    list_missing_templates,
)
from features.politiques.injector import (
    update_shopify_policies,
    fetch_page_by_handle,
    create_page,
    update_page,
    generate_injection_report,
)


BASE_URL = "https://test.myshopify.com/admin/api/2026-01"
HEADERS  = {"X-Shopify-Access-Token": "test"}

LEGAL_INFO = {
    "company_name":    "Test SAS",
    "email":           "contact@test.com",
    "phone":           "+33 1 23 45 67 89",
    "address":         "1 rue Test, 75001 Paris",
    "siret":           "123 456 789 00012",
    "processing_time": "2-3 jours ouvrés",
    "shipping_delay":  "5-7 jours ouvrés",
    "website_url":     "https://www.test.com",
}


# ── load_template ─────────────────────────────────────────────────────────────

class TestLoadTemplate(unittest.TestCase):

    def test_loads_existing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            pol_dir = os.path.join(tmp, "politiques")
            os.makedirs(pol_dir)
            path = os.path.join(pol_dir, "politique_retour.html")
            with open(path, "w", encoding="utf-8") as f:
                f.write("<p>Retour {{email}}</p>")
            result = load_template(tmp, "politique_retour.html")
        self.assertEqual(result, "<p>Retour {{email}}</p>")

    def test_returns_none_if_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = load_template(tmp, "politique_retour.html")
        self.assertIsNone(result)

    def test_reads_utf8_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            pol_dir = os.path.join(tmp, "politiques")
            os.makedirs(pol_dir)
            content = "<p>Délai de réception : {{processing_time}}</p>"
            with open(os.path.join(pol_dir, "test.html"), "w", encoding="utf-8") as f:
                f.write(content)
            result = load_template(tmp, "test.html")
        self.assertIn("Délai", result)


# ── fill_placeholders ─────────────────────────────────────────────────────────

class TestFillPlaceholders(unittest.TestCase):

    def test_replaces_email(self):
        result = fill_placeholders("<p>{{email}}</p>", "Ma Boutique", LEGAL_INFO)
        self.assertIn("contact@test.com", result)
        self.assertNotIn("{{email}}", result)

    def test_replaces_store_name(self):
        result = fill_placeholders("<p>{{store_name}}</p>", "Ma Boutique", LEGAL_INFO)
        self.assertIn("Ma Boutique", result)

    def test_replaces_company_name(self):
        result = fill_placeholders("<p>{{company_name}}</p>", "B", LEGAL_INFO)
        self.assertIn("Test SAS", result)

    def test_replaces_siret(self):
        result = fill_placeholders("SIRET : {{siret}}", "B", LEGAL_INFO)
        self.assertIn("123 456 789 00012", result)

    def test_replaces_processing_time(self):
        result = fill_placeholders("{{processing_time}}", "B", LEGAL_INFO)
        self.assertIn("2-3 jours ouvrés", result)

    def test_replaces_shipping_delay(self):
        result = fill_placeholders("{{shipping_delay}}", "B", LEGAL_INFO)
        self.assertIn("5-7 jours ouvrés", result)

    def test_builds_url_remboursement(self):
        result = fill_placeholders("{{url_remboursement}}", "B", LEGAL_INFO)
        self.assertEqual(result.strip(), "https://www.test.com/policies/refund-policy")

    def test_builds_url_confidentialite(self):
        result = fill_placeholders("{{url_confidentialite}}", "B", LEGAL_INFO)
        self.assertIn("/policies/privacy-policy", result)

    def test_builds_url_mentions_legales(self):
        result = fill_placeholders("{{url_mentions_legales}}", "B", LEGAL_INFO)
        self.assertIn("/policies/legal-notice", result)

    def test_builds_url_page_retour(self):
        result = fill_placeholders("{{url_page_retour}}", "B", LEGAL_INFO)
        self.assertIn("/pages/return-policy", result)

    def test_trailing_slash_stripped_from_website_url(self):
        info = {**LEGAL_INFO, "website_url": "https://www.test.com/"}
        result = fill_placeholders("{{url_remboursement}}", "B", info)
        self.assertNotIn("//policies", result)

    def test_all_placeholders_replaced_no_leftover(self):
        template = (
            "{{store_name}} {{company_name}} {{email}} {{phone}} {{address}} "
            "{{siret}} {{processing_time}} {{shipping_delay}} {{website_url}} "
            "{{url_remboursement}} {{url_confidentialite}} {{url_conditions_service}} "
            "{{url_expedition}} {{url_coordonnees}} {{url_conditions_vente}} "
            "{{url_mentions_legales}} {{url_page_retour}} {{date_injection}}"
        )
        result = fill_placeholders(template, "Boutique", LEGAL_INFO)
        import re
        remaining = re.findall(r"\{\{[^}]+\}\}", result)
        self.assertEqual(remaining, [])

    def test_missing_field_replaced_with_empty_string(self):
        info = {}  # tous les champs manquants
        result = fill_placeholders("{{email}}", "B", info)
        self.assertEqual(result, "")


# ── list_missing_templates ────────────────────────────────────────────────────

class TestListMissingTemplates(unittest.TestCase):

    def test_all_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            pol_dir = os.path.join(tmp, "politiques")
            os.makedirs(pol_dir)
            for f in ["a.html", "b.html"]:
                open(os.path.join(pol_dir, f), "w").close()
            result = list_missing_templates(tmp, ["a.html", "b.html"])
        self.assertEqual(result, [])

    def test_some_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            pol_dir = os.path.join(tmp, "politiques")
            os.makedirs(pol_dir)
            open(os.path.join(pol_dir, "a.html"), "w").close()
            result = list_missing_templates(tmp, ["a.html", "b.html"])
        self.assertEqual(result, ["b.html"])

    def test_all_missing(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = list_missing_templates(tmp, ["a.html", "b.html"])
        self.assertEqual(result, ["a.html", "b.html"])

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = list_missing_templates(tmp, [])
        self.assertEqual(result, [])


# ── update_shopify_policies ───────────────────────────────────────────────────

class TestUpdateShopifyPolicies(unittest.TestCase):

    def _make_policies(self):
        return [
            {"type": "REFUND_POLICY",  "body": "<p>Retour</p>",  "label": "Politique retour"},
            {"type": "PRIVACY_POLICY", "body": "<p>Privé</p>",   "label": "Confidentialité"},
        ]

    @patch("features.politiques.injector.graphql_request")
    def test_success(self, mock_gql):
        mock_gql.return_value = {
            "data": {"shopPoliciesUpdate": {
                "shopPolicies": [
                    {"type": "REFUND_POLICY",  "url": "/policies/refund-policy"},
                    {"type": "PRIVACY_POLICY", "url": "/policies/privacy-policy"},
                ],
                "userErrors": [],
            }}
        }
        results = update_shopify_policies(self._make_policies(), BASE_URL, HEADERS)
        self.assertEqual(len(results), 2)
        self.assertTrue(all(r["statut"] == "OK" for r in results))

    @patch("features.politiques.injector.graphql_request")
    def test_all_sent_in_one_call(self, mock_gql):
        mock_gql.return_value = {
            "data": {"shopPoliciesUpdate": {"shopPolicies": [], "userErrors": []}}
        }
        update_shopify_policies(self._make_policies(), BASE_URL, HEADERS)
        self.assertEqual(mock_gql.call_count, 1)
        variables = mock_gql.call_args.args[3]
        self.assertEqual(len(variables["policies"]), 2)

    @patch("features.politiques.injector.graphql_request")
    def test_user_errors_marks_erreur(self, mock_gql):
        mock_gql.return_value = {
            "data": {"shopPoliciesUpdate": {
                "shopPolicies": [],
                "userErrors": [{"field": "REFUND_POLICY", "message": "Invalid body"}],
            }}
        }
        results = update_shopify_policies(self._make_policies(), BASE_URL, HEADERS)
        statuts = {r["type"]: r["statut"] for r in results}
        self.assertEqual(statuts["REFUND_POLICY"], "ERREUR")

    @patch("features.politiques.injector.graphql_request")
    def test_exception_marks_all_erreur(self, mock_gql):
        mock_gql.side_effect = Exception("Network error")
        results = update_shopify_policies(self._make_policies(), BASE_URL, HEADERS)
        self.assertTrue(all(r["statut"] == "ERREUR" for r in results))
        self.assertIn("Network error", results[0]["erreur"])

    @patch("features.politiques.injector.graphql_request")
    def test_url_populated_on_success(self, mock_gql):
        mock_gql.return_value = {
            "data": {"shopPoliciesUpdate": {
                "shopPolicies": [{"type": "REFUND_POLICY", "url": "/policies/refund-policy"}],
                "userErrors": [],
            }}
        }
        results = update_shopify_policies(
            [{"type": "REFUND_POLICY", "body": "<p>R</p>", "label": "Retour"}],
            BASE_URL, HEADERS
        )
        self.assertEqual(results[0]["url"], "/policies/refund-policy")


# ── fetch_page_by_handle ──────────────────────────────────────────────────────

class TestFetchPageByHandle(unittest.TestCase):

    @patch("features.politiques.injector.shopify_get")
    def test_found(self, mock_get):
        mock_get.return_value = {
            "pages": [{"id": 1, "handle": "return-policy", "title": "Politique De Retour"}]
        }
        result = fetch_page_by_handle("return-policy", BASE_URL, HEADERS)
        self.assertEqual(result["id"], 1)

    @patch("features.politiques.injector.shopify_get")
    def test_not_found(self, mock_get):
        mock_get.return_value = {"pages": []}
        result = fetch_page_by_handle("return-policy", BASE_URL, HEADERS)
        self.assertIsNone(result)

    @patch("features.politiques.injector.shopify_get")
    def test_handle_mismatch_returns_none(self, mock_get):
        mock_get.return_value = {
            "pages": [{"id": 2, "handle": "autre-page", "title": "Autre"}]
        }
        result = fetch_page_by_handle("return-policy", BASE_URL, HEADERS)
        self.assertIsNone(result)


# ── create_page ───────────────────────────────────────────────────────────────

class TestCreatePage(unittest.TestCase):

    @patch("features.politiques.injector.shopify_post")
    def test_creates_page(self, mock_post):
        mock_post.return_value = {"page": {"id": 10, "handle": "return-policy"}}
        result = create_page("Politique De Retour", "return-policy", "<p>body</p>", BASE_URL, HEADERS)
        self.assertEqual(result["id"], 10)

    @patch("features.politiques.injector.shopify_post")
    def test_payload_correct(self, mock_post):
        mock_post.return_value = {"page": {"id": 10}}
        create_page("Titre", "mon-handle", "<p>html</p>", BASE_URL, HEADERS)
        payload = mock_post.call_args.args[2]
        self.assertEqual(payload["page"]["title"],     "Titre")
        self.assertEqual(payload["page"]["handle"],    "mon-handle")
        self.assertEqual(payload["page"]["body_html"], "<p>html</p>")
        self.assertTrue(payload["page"]["published"])

    @patch("features.politiques.injector.shopify_post")
    def test_returns_none_on_exception(self, mock_post):
        mock_post.side_effect = Exception("Error")
        result = create_page("T", "h", "<p>b</p>", BASE_URL, HEADERS)
        self.assertIsNone(result)


# ── update_page ───────────────────────────────────────────────────────────────

class TestUpdatePage(unittest.TestCase):

    @patch("features.politiques.injector.shopify_put")
    def test_updates_page(self, mock_put):
        mock_put.return_value = {"page": {"id": 10}}
        result = update_page(10, "Titre", "<p>new</p>", BASE_URL, HEADERS)
        self.assertEqual(result["id"], 10)

    @patch("features.politiques.injector.shopify_put")
    def test_payload_correct(self, mock_put):
        mock_put.return_value = {"page": {"id": 5}}
        update_page(5, "Titre MAJ", "<p>html</p>", BASE_URL, HEADERS)
        payload = mock_put.call_args.args[2]
        self.assertEqual(payload["page"]["id"],        5)
        self.assertEqual(payload["page"]["title"],     "Titre MAJ")
        self.assertEqual(payload["page"]["body_html"], "<p>html</p>")

    @patch("features.politiques.injector.shopify_put")
    def test_returns_none_on_exception(self, mock_put):
        mock_put.side_effect = Exception("Error")
        result = update_page(5, "T", "<p>b</p>", BASE_URL, HEADERS)
        self.assertIsNone(result)


# ── generate_injection_report ─────────────────────────────────────────────────

class TestGenerateInjectionReport(unittest.TestCase):

    def _make_log(self):
        return [
            {"label": "Politique retour", "type": "REFUND_POLICY",  "cible": "Shopify Settings",
             "statut": "OK",     "url": "/policies/refund-policy", "erreur": ""},
            {"label": "Confidentialité",  "type": "PRIVACY_POLICY", "cible": "Shopify Settings",
             "statut": "ERREUR", "url": "",                         "erreur": "Timeout"},
        ]

    def test_creates_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            self.assertTrue(os.path.exists(path))

    def test_filename_starts_with_politiques_rapport(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
        self.assertTrue(os.path.basename(path).startswith("politiques_rapport_"))
        self.assertTrue(path.endswith(".csv"))

    def test_csv_has_correct_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                fieldnames = csv.DictReader(f).fieldnames
        for col in ["date_heure", "label", "type", "cible", "statut", "url", "erreur"]:
            self.assertIn(col, fieldnames)

    def test_csv_row_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)

    def test_statut_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                statuts = [r["statut"] for r in csv.DictReader(f)]
        self.assertIn("OK", statuts)
        self.assertIn("ERREUR", statuts)

    def test_empty_log(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report([], tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
