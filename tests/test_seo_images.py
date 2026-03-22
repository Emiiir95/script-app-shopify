#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_seo_images.py — Tests unitaires pour features/seo_images/

Couvre :
  - slugify_title   : conversion titre → slug SEO
  - _get_extension  : extraction extension depuis URL CDN
  - update_images_seo : mutation GraphQL fileUpdate (batches, retry, erreurs)
  - generate_injection_report : création CSV post-injection horodaté
"""

import csv
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

from features.seo_images.injector import (
    slugify_title,
    _get_extension,
    update_images_seo,
    generate_injection_report,
)


# ── slugify_title ──────────────────────────────────────────────────────────────

class TestSlugifyTitle(unittest.TestCase):

    def test_basic_ascii(self):
        self.assertEqual(slugify_title("Hello World"), "hello-world")

    def test_accents_removed(self):
        self.assertEqual(slugify_title("Arbre à Chat"), "arbre-a-chat")

    def test_em_dash_removed(self):
        result = slugify_title("Arbre à Chat – Balaitous")
        self.assertNotIn("–", result)
        self.assertIn("arbre-a-chat", result)

    def test_multiple_spaces_collapsed(self):
        self.assertEqual(slugify_title("hello   world"), "hello-world")

    def test_trailing_leading_hyphens_stripped(self):
        result = slugify_title("  Hello  ")
        self.assertFalse(result.startswith("-"))
        self.assertFalse(result.endswith("-"))

    def test_max_80_chars(self):
        long_title = "A" * 100
        self.assertLessEqual(len(slugify_title(long_title)), 80)

    def test_uppercase_lowercased(self):
        self.assertEqual(slugify_title("ARBRE CHAT"), "arbre-chat")

    def test_numbers_kept(self):
        self.assertIn("123", slugify_title("Produit 123"))

    def test_empty_string(self):
        self.assertEqual(slugify_title(""), "")


# ── _get_extension ─────────────────────────────────────────────────────────────

class TestGetExtension(unittest.TestCase):

    def test_jpg(self):
        self.assertEqual(_get_extension("https://cdn.shopify.com/s/files/1/image.jpg?v=123"), ".jpg")

    def test_jpeg(self):
        self.assertEqual(_get_extension("https://cdn.shopify.com/s/files/1/image.jpeg"), ".jpeg")

    def test_png(self):
        self.assertEqual(_get_extension("https://cdn.shopify.com/s/files/1/image.png?v=1"), ".png")

    def test_webp(self):
        self.assertEqual(_get_extension("https://cdn.shopify.com/s/files/1/image.webp"), ".webp")

    def test_gif(self):
        self.assertEqual(_get_extension("https://cdn.shopify.com/s/files/1/image.gif"), ".gif")

    def test_unknown_extension_defaults_to_jpg(self):
        self.assertEqual(_get_extension("https://cdn.shopify.com/s/files/1/image.bmp"), ".jpg")

    def test_no_extension_defaults_to_jpg(self):
        self.assertEqual(_get_extension("https://cdn.shopify.com/s/files/1/image"), ".jpg")

    def test_uppercase_lowercased(self):
        self.assertEqual(_get_extension("https://cdn.shopify.com/s/files/1/image.JPG"), ".jpg")


# ── update_images_seo ─────────────────────────────────────────────────────────

BASE_URL = "https://test.myshopify.com/admin/api/2026-01"
HEADERS  = {"X-Shopify-Access-Token": "test"}


def _make_image_updates(n=1, start_pos=1):
    return [
        {
            "gid":      f"gid://shopify/MediaImage/{100 + i}",
            "filename": f"test-produit-{i}.jpg",
            "alt":      "Test Produit",
            "handle":   "test-produit",
            "position": i,
        }
        for i in range(start_pos, start_pos + n)
    ]


class TestUpdateImagesSeo(unittest.TestCase):

    @patch("features.seo_images.injector.graphql_request")
    def test_single_image_success(self, mock_gql):
        gid = "gid://shopify/MediaImage/101"
        mock_gql.return_value = {
            "data": {"fileUpdate": {
                "files": [{"id": gid, "alt": "Test Produit", "image": {"url": "https://cdn.new/img.jpg"}}],
                "userErrors": [],
            }}
        }
        updates = _make_image_updates(1)
        results = update_images_seo(updates, BASE_URL, HEADERS)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["statut"], "OK")
        self.assertEqual(results[0]["filename_new"], "test-produit-1.jpg")
        self.assertEqual(results[0]["alt_new"], "Test Produit")

    @patch("features.seo_images.injector.graphql_request")
    def test_batch_of_10_sends_one_call(self, mock_gql):
        gid = "gid://shopify/MediaImage/101"
        mock_gql.return_value = {
            "data": {"fileUpdate": {
                "files": [{"id": f"gid://shopify/MediaImage/{100+i}", "alt": "Test", "image": {"url": ""}} for i in range(1, 11)],
                "userErrors": [],
            }}
        }
        updates = _make_image_updates(10)
        results = update_images_seo(updates, BASE_URL, HEADERS)

        self.assertEqual(mock_gql.call_count, 1)
        self.assertEqual(len(results), 10)

    @patch("features.seo_images.injector.graphql_request")
    def test_11_images_sends_two_calls(self, mock_gql):
        def side_effect(base_url, headers, mutation, variables):
            return {
                "data": {"fileUpdate": {
                    "files": [{"id": f["id"], "alt": "T", "image": {"url": ""}} for f in variables["files"]],
                    "userErrors": [],
                }}
            }
        mock_gql.side_effect = side_effect

        updates = _make_image_updates(11)
        results = update_images_seo(updates, BASE_URL, HEADERS)

        self.assertEqual(mock_gql.call_count, 2)
        self.assertEqual(len(results), 11)

    @patch("features.seo_images.injector.graphql_request")
    def test_user_errors_triggers_retry(self, mock_gql):
        mock_gql.side_effect = [
            {"data": {"fileUpdate": {"files": [], "userErrors": [{"field": "id", "message": "Invalid"}]}}},
            {"data": {"fileUpdate": {"files": [], "userErrors": [{"field": "id", "message": "Invalid"}]}}},
            {"data": {"fileUpdate": {"files": [], "userErrors": [{"field": "id", "message": "Invalid"}]}}},
        ]
        updates = _make_image_updates(1)
        results = update_images_seo(updates, BASE_URL, HEADERS, max_retries=3)

        self.assertEqual(mock_gql.call_count, 3)
        self.assertEqual(results[0]["statut"], "ERREUR")

    @patch("features.seo_images.injector.graphql_request")
    def test_exception_triggers_retry_then_error(self, mock_gql):
        mock_gql.side_effect = Exception("Network error")
        updates = _make_image_updates(1)
        results = update_images_seo(updates, BASE_URL, HEADERS, max_retries=2)

        self.assertEqual(mock_gql.call_count, 2)
        self.assertEqual(results[0]["statut"], "ERREUR")
        self.assertIn("Network error", results[0]["erreur"])

    @patch("features.seo_images.injector.graphql_request")
    def test_retry_succeeds_on_second_attempt(self, mock_gql):
        gid = "gid://shopify/MediaImage/101"
        mock_gql.side_effect = [
            Exception("Timeout"),
            {"data": {"fileUpdate": {"files": [{"id": gid, "alt": "Test", "image": {"url": "https://cdn.new/img.jpg"}}], "userErrors": []}}},
        ]
        updates = _make_image_updates(1)
        results = update_images_seo(updates, BASE_URL, HEADERS, max_retries=3)

        self.assertEqual(results[0]["statut"], "OK")

    @patch("features.seo_images.injector.graphql_request")
    def test_result_contains_url_new(self, mock_gql):
        gid = "gid://shopify/MediaImage/101"
        mock_gql.return_value = {
            "data": {"fileUpdate": {
                "files": [{"id": gid, "alt": "Test", "image": {"url": "https://cdn.shopify.com/new.jpg"}}],
                "userErrors": [],
            }}
        }
        updates = _make_image_updates(1)
        results = update_images_seo(updates, BASE_URL, HEADERS)
        self.assertEqual(results[0]["url_new"], "https://cdn.shopify.com/new.jpg")

    @patch("features.seo_images.injector.graphql_request")
    def test_empty_updates_returns_empty(self, mock_gql):
        results = update_images_seo([], BASE_URL, HEADERS)
        self.assertEqual(results, [])
        mock_gql.assert_not_called()

    @patch("features.seo_images.injector.graphql_request")
    def test_result_has_handle_and_position(self, mock_gql):
        gid = "gid://shopify/MediaImage/101"
        mock_gql.return_value = {
            "data": {"fileUpdate": {
                "files": [{"id": gid, "alt": "Test", "image": {"url": ""}}],
                "userErrors": [],
            }}
        }
        updates = [{
            "gid": gid, "filename": "test-1.jpg", "alt": "Test",
            "handle": "mon-produit", "position": 2,
        }]
        results = update_images_seo(updates, BASE_URL, HEADERS)
        self.assertEqual(results[0]["handle"], "mon-produit")
        self.assertEqual(results[0]["position"], 2)


# ── generate_injection_report ─────────────────────────────────────────────────

class TestGenerateInjectionReport(unittest.TestCase):

    def _make_log(self):
        return [
            {
                "handle": "prod-1", "position": 1,
                "gid": "gid://shopify/MediaImage/101",
                "filename_new": "prod-1-1.jpg", "alt_new": "Produit 1",
                "url_new": "https://cdn.new/prod-1-1.jpg",
                "statut": "OK", "erreur": "",
            },
            {
                "handle": "prod-2", "position": 1,
                "gid": "gid://shopify/MediaImage/201",
                "filename_new": "prod-2-1.jpg", "alt_new": "Produit 2",
                "url_new": "",
                "statut": "ERREUR", "erreur": "Timeout",
            },
        ]

    def test_creates_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            self.assertTrue(os.path.exists(path))

    def test_csv_has_correct_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                fieldnames = csv.DictReader(f).fieldnames
        expected = ["date_heure", "handle", "position", "gid",
                    "filename_new", "alt_new", "url_new", "statut", "erreur"]
        for col in expected:
            self.assertIn(col, fieldnames)

    def test_csv_has_correct_row_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 2)

    def test_csv_statut_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                statuts = [r["statut"] for r in csv.DictReader(f)]
        self.assertIn("OK", statuts)
        self.assertIn("ERREUR", statuts)

    def test_filename_starts_with_seo_images_rapport(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            filename = os.path.basename(path)
        self.assertTrue(filename.startswith("seo_images_rapport_"))
        self.assertTrue(filename.endswith(".csv"))

    def test_empty_log_creates_empty_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report([], tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
