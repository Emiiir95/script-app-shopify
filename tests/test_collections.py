#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_collections.py — Tests unitaires pour features/collections/

Couvre :
  - generator  : load_keywords_for_collection, generate_collection_description,
                 generate_collection_meta_title, generate_collection_meta_desc
  - injector   : get_handle_from_url, find_collection_by_handle,
                 fetch_existing_collections, create_collection,
                 update_collection, generate_injection_report
"""

import csv
import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

from features.collections.generator import (
    load_keywords_for_collection,
    generate_collection_description,
    generate_collection_meta_title,
    generate_collection_meta_desc,
)
from features.collections.injector import (
    get_handle_from_url,
    find_collection_by_handle,
    fetch_existing_collections,
    create_collection,
    update_collection,
    generate_injection_report,
)


# ── load_keywords_for_collection ──────────────────────────────────────────────

class TestLoadKeywordsForCollection(unittest.TestCase):

    def _make_keywords_csv(self, tmpdir, rows):
        """Crée un keywords.csv dans tmpdir/seo_boost/keywords.csv."""
        seo_dir = os.path.join(tmpdir, "seo_boost")
        os.makedirs(seo_dir, exist_ok=True)
        path = os.path.join(seo_dir, "keywords.csv")
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["Keyword", "Volume"])
            writer.writeheader()
            for row in rows:
                writer.writerow(row)
        return tmpdir

    def test_returns_empty_if_no_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = load_keywords_for_collection(tmp, ["arbre chat"])
        self.assertEqual(result, "")

    def test_returns_matching_keywords(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_keywords_csv(tmp, [
                {"Keyword": "arbre a chat xxl", "Volume": "1000"},
                {"Keyword": "veilleuse bebe",   "Volume": "500"},
            ])
            result = load_keywords_for_collection(tmp, ["arbre chat"])
        self.assertIn("arbre a chat xxl", result)
        self.assertNotIn("veilleuse bebe", result)

    def test_filters_by_tag_words(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_keywords_csv(tmp, [
                {"Keyword": "arbre a chat grand", "Volume": "800"},
                {"Keyword": "lit pour chat",      "Volume": "600"},
                {"Keyword": "griffoir mural",     "Volume": "400"},
            ])
            result = load_keywords_for_collection(tmp, ["arbre a chat"])
        self.assertIn("arbre a chat grand", result)
        self.assertIn("lit pour chat", result)
        self.assertNotIn("griffoir mural", result)

    def test_sorts_by_volume_desc(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_keywords_csv(tmp, [
                {"Keyword": "arbre chat petit", "Volume": "100"},
                {"Keyword": "arbre chat xxl",   "Volume": "5000"},
                {"Keyword": "arbre chat bois",  "Volume": "1000"},
            ])
            result = load_keywords_for_collection(tmp, ["arbre"])
        lines = [l for l in result.splitlines() if l.startswith("-")]
        self.assertIn("5,000", lines[0])  # volume le plus haut en premier

    def test_keeps_max_15_keywords(self):
        rows = [{"Keyword": f"arbre chat kw{i}", "Volume": str(i * 10)} for i in range(20)]
        with tempfile.TemporaryDirectory() as tmp:
            self._make_keywords_csv(tmp, rows)
            result = load_keywords_for_collection(tmp, ["arbre"])
        lines = [l for l in result.splitlines() if l.startswith("-")]
        self.assertLessEqual(len(lines), 15)

    def test_returns_empty_if_no_match(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_keywords_csv(tmp, [
                {"Keyword": "veilleuse bebe", "Volume": "500"},
            ])
            result = load_keywords_for_collection(tmp, ["arbre chat"])
        self.assertEqual(result, "")

    def test_volume_with_comma_parsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            self._make_keywords_csv(tmp, [
                {"Keyword": "arbre chat xxl", "Volume": "1,200"},
            ])
            result = load_keywords_for_collection(tmp, ["arbre"])
        self.assertIn("arbre chat xxl", result)

    def test_short_words_ignored_in_tags(self):
        """Les mots de 2 caractères ou moins ne servent pas au matching."""
        with tempfile.TemporaryDirectory() as tmp:
            self._make_keywords_csv(tmp, [
                {"Keyword": "un arbre", "Volume": "100"},
            ])
            # Tag "un" (2 chars) → ignoré → aucun match
            result = load_keywords_for_collection(tmp, ["un"])
        self.assertEqual(result, "")


# ── generate_collection_description ──────────────────────────────────────────

class TestGenerateCollectionDescription(unittest.TestCase):

    def _mock_client(self, content):
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = content
        resp.usage = MagicMock(prompt_tokens=100, completion_tokens=200)
        client.chat.completions.create.return_value = resp
        return client

    def _mock_tracker(self):
        tracker = MagicMock()
        return tracker

    def test_returns_html_on_success(self):
        client  = self._mock_client("<p>Description de la collection.</p>")
        tracker = self._mock_tracker()
        result  = generate_collection_description("Col XXL", "Arbre Chat", ["arbre chat xxl"], "", client, tracker)
        self.assertIn("<p>", result)

    def test_strips_markdown_code_block(self):
        client  = self._mock_client("```html\n<p>Description.</p>\n```")
        tracker = self._mock_tracker()
        result  = generate_collection_description("Col XXL", "Arbre Chat", ["arbre chat xxl"], "", client, tracker)
        self.assertNotIn("```", result)
        self.assertIn("<p>", result)

    def test_strips_markdown_without_language(self):
        client  = self._mock_client("```\n<p>Description.</p>\n```")
        tracker = self._mock_tracker()
        result  = generate_collection_description("Col XXL", "Arbre Chat", ["arbre chat xxl"], "", client, tracker)
        self.assertNotIn("```", result)

    def test_fallback_on_all_failures(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API error")
        tracker = self._mock_tracker()
        result  = generate_collection_description("Col XXL", "Arbre Chat", ["arbre chat xxl"], "", client, tracker, max_retries=2)
        self.assertIn("Col XXL", result)
        self.assertIn("<p>", result)

    def test_retry_then_success(self):
        client = MagicMock()
        resp_ok = MagicMock()
        resp_ok.choices[0].message.content = "<p>OK</p>"
        resp_ok.usage = MagicMock(prompt_tokens=10, completion_tokens=20)
        client.chat.completions.create.side_effect = [Exception("fail"), resp_ok]
        tracker = self._mock_tracker()
        result  = generate_collection_description("Col", "Niche", [], "", client, tracker, max_retries=3)
        self.assertEqual(result, "<p>OK</p>")
        self.assertEqual(client.chat.completions.create.call_count, 2)

    def test_uses_gpt4o_model(self):
        client  = self._mock_client("<p>desc</p>")
        tracker = self._mock_tracker()
        generate_collection_description("Col", "Niche", [], "", client, tracker)
        call_kwargs = client.chat.completions.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], "gpt-4o")


# ── generate_collection_meta_title ────────────────────────────────────────────

class TestGenerateCollectionMetaTitle(unittest.TestCase):

    def _mock_client(self, json_content):
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = json.dumps(json_content)
        resp.usage = MagicMock(prompt_tokens=10, completion_tokens=10)
        client.chat.completions.create.return_value = resp
        return client

    def test_returns_meta_title_on_success(self):
        client  = self._mock_client({"meta_title": "Arbre à Chat XXL – Sélection Premium"})
        tracker = MagicMock()
        result  = generate_collection_meta_title("Arbre à Chat XXL", "Arbre Chat", [], client, tracker)
        self.assertEqual(result, "Arbre à Chat XXL – Sélection Premium")

    def test_fallback_on_failure(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("fail")
        tracker = MagicMock()
        result  = generate_collection_meta_title("Col XXL", "Arbre Chat", [], client, tracker, max_retries=1)
        self.assertIn("Col XXL", result)

    def test_fallback_truncated_to_70(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("fail")
        tracker = MagicMock()
        result  = generate_collection_meta_title("A" * 80, "B" * 80, [], client, tracker, max_retries=1)
        self.assertLessEqual(len(result), 70)

    def test_uses_gpt4o_mini_model(self):
        client  = self._mock_client({"meta_title": "Titre"})
        tracker = MagicMock()
        generate_collection_meta_title("Col", "Niche", [], client, tracker)
        call_kwargs = client.chat.completions.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], "gpt-4o-mini")

    def test_empty_meta_title_triggers_fallback(self):
        client  = self._mock_client({"meta_title": ""})
        tracker = MagicMock()
        result  = generate_collection_meta_title("Col XXL", "Arbre Chat", [], client, tracker, max_retries=1)
        self.assertIn("Col XXL", result)


# ── generate_collection_meta_desc ─────────────────────────────────────────────

class TestGenerateCollectionMetaDesc(unittest.TestCase):

    def _mock_client(self, json_content):
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = json.dumps(json_content)
        resp.usage = MagicMock(prompt_tokens=10, completion_tokens=10)
        client.chat.completions.create.return_value = resp
        return client

    def test_returns_meta_desc_on_success(self):
        client  = self._mock_client({"meta_description": "Découvrez notre collection d'arbres à chat XXL."})
        tracker = MagicMock()
        result  = generate_collection_meta_desc("Arbre Chat XXL", "Arbre Chat", [], client, tracker)
        self.assertIn("Découvrez", result)

    def test_fallback_on_failure(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("fail")
        tracker = MagicMock()
        result  = generate_collection_meta_desc("Col XXL", "Arbre Chat", [], client, tracker, max_retries=1)
        self.assertIn("Col XXL", result)

    def test_uses_gpt4o_mini_model(self):
        client  = self._mock_client({"meta_description": "desc"})
        tracker = MagicMock()
        generate_collection_meta_desc("Col", "Niche", [], client, tracker)
        call_kwargs = client.chat.completions.create.call_args
        self.assertEqual(call_kwargs.kwargs["model"], "gpt-4o-mini")

    def test_empty_desc_triggers_fallback(self):
        client  = self._mock_client({"meta_description": ""})
        tracker = MagicMock()
        result  = generate_collection_meta_desc("Col XXL", "Arbre Chat", [], client, tracker, max_retries=1)
        self.assertIn("Col XXL", result)


# ── get_handle_from_url ───────────────────────────────────────────────────────

class TestGetHandleFromUrl(unittest.TestCase):

    def test_standard_url(self):
        self.assertEqual(
            get_handle_from_url("https://le-perchoir-du-chat.com/collections/arbre-a-chat-xxl"),
            "arbre-a-chat-xxl"
        )

    def test_trailing_slash(self):
        self.assertEqual(
            get_handle_from_url("https://example.com/collections/mon-handle/"),
            "mon-handle"
        )

    def test_short_url(self):
        self.assertEqual(get_handle_from_url("https://example.com/collections/test"), "test")


# ── find_collection_by_handle ─────────────────────────────────────────────────

class TestFindCollectionByHandle(unittest.TestCase):

    def setUp(self):
        self.existing = [
            {"id": 1, "handle": "arbre-a-chat-xxl", "title": "Arbre XXL"},
            {"id": 2, "handle": "arbre-a-chat-led",  "title": "Arbre LED"},
        ]

    def test_found(self):
        result = find_collection_by_handle("arbre-a-chat-xxl", self.existing)
        self.assertEqual(result["id"], 1)

    def test_not_found(self):
        result = find_collection_by_handle("inexistant", self.existing)
        self.assertIsNone(result)

    def test_empty_list(self):
        result = find_collection_by_handle("arbre-a-chat-xxl", [])
        self.assertIsNone(result)


# ── fetch_existing_collections ────────────────────────────────────────────────

class TestFetchExistingCollections(unittest.TestCase):

    @patch("features.collections.injector.shopify_get")
    def test_returns_collections(self, mock_get):
        mock_get.return_value = {
            "smart_collections": [
                {"id": 1, "handle": "col-1", "title": "Col 1"},
                {"id": 2, "handle": "col-2", "title": "Col 2"},
            ]
        }
        result = fetch_existing_collections("http://test.com", {})
        self.assertEqual(len(result), 2)

    @patch("features.collections.injector.shopify_get")
    def test_pagination_via_since_id(self, mock_get):
        batch_250 = [{"id": i, "handle": f"col-{i}", "title": f"Col {i}"} for i in range(250)]
        batch_5   = [{"id": i, "handle": f"col-{i}", "title": f"Col {i}"} for i in range(250, 255)]
        mock_get.side_effect = [
            {"smart_collections": batch_250},
            {"smart_collections": batch_5},
        ]
        result = fetch_existing_collections("http://test.com", {})
        self.assertEqual(len(result), 255)
        self.assertEqual(mock_get.call_count, 2)

    @patch("features.collections.injector.shopify_get")
    def test_returns_empty_if_none(self, mock_get):
        mock_get.return_value = {"smart_collections": []}
        result = fetch_existing_collections("http://test.com", {})
        self.assertEqual(result, [])


# ── create_collection ─────────────────────────────────────────────────────────

BASE_URL = "https://test.myshopify.com/admin/api/2026-01"
HEADERS  = {"X-Shopify-Access-Token": "test"}

COL_CONFIG = {
    "name": "Arbre à Chat XXL",
    "tags": ["arbre a chat xxl", "arbre chat grand"],
    "url":  "https://le-perchoir-du-chat.com/collections/arbre-a-chat-xxl",
    "volume": 1900,
}


class TestCreateCollection(unittest.TestCase):

    @patch("features.collections.injector.shopify_post")
    @patch("features.collections.injector.shopify_get")
    def test_creates_collection_and_sets_metafields(self, mock_get, mock_post):
        mock_post.return_value = {"smart_collection": {"id": 42, "handle": "arbre-a-chat-xxl"}}
        mock_get.return_value  = {"metafields": []}

        result = create_collection(COL_CONFIG, "<p>desc</p>", "Meta Title", "Meta desc", BASE_URL, HEADERS)

        self.assertEqual(result["id"], 42)
        # POST initial pour créer la collection
        first_call = mock_post.call_args_list[0]
        self.assertIn("smart_collections.json", first_call.args[0])

    @patch("features.collections.injector.shopify_post")
    @patch("features.collections.injector.shopify_get")
    def test_sets_title_tag_metafield(self, mock_get, mock_post):
        mock_post.return_value = {"smart_collection": {"id": 42}}
        mock_get.return_value  = {"metafields": []}

        create_collection(COL_CONFIG, "<p>desc</p>", "Mon Meta Title", "Meta desc", BASE_URL, HEADERS)

        # Vérifier qu'un POST metafield avec title_tag a été envoyé
        metafield_posts = [
            c for c in mock_post.call_args_list
            if "metafields" in c.args[0]
        ]
        keys_posted = [c.args[2]["metafield"]["key"] for c in metafield_posts]
        self.assertIn("title_tag", keys_posted)

    @patch("features.collections.injector.shopify_post")
    @patch("features.collections.injector.shopify_get")
    def test_sets_description_tag_metafield(self, mock_get, mock_post):
        mock_post.return_value = {"smart_collection": {"id": 42}}
        mock_get.return_value  = {"metafields": []}

        create_collection(COL_CONFIG, "<p>desc</p>", "Title", "Ma meta description", BASE_URL, HEADERS)

        metafield_posts = [
            c for c in mock_post.call_args_list
            if "metafields" in c.args[0]
        ]
        keys_posted = [c.args[2]["metafield"]["key"] for c in metafield_posts]
        self.assertIn("description_tag", keys_posted)

    @patch("features.collections.injector.shopify_post")
    def test_returns_none_on_exception(self, mock_post):
        mock_post.side_effect = Exception("Shopify error")
        result = create_collection(COL_CONFIG, "<p>desc</p>", "Title", "Desc", BASE_URL, HEADERS)
        self.assertIsNone(result)

    @patch("features.collections.injector.shopify_post")
    @patch("features.collections.injector.shopify_get")
    def test_rules_built_from_tags(self, mock_get, mock_post):
        mock_post.return_value = {"smart_collection": {"id": 1}}
        mock_get.return_value  = {"metafields": []}

        create_collection(COL_CONFIG, "<p>desc</p>", "T", "D", BASE_URL, HEADERS)

        payload = mock_post.call_args_list[0].args[2]
        rules   = payload["smart_collection"]["rules"]
        conditions = [r["condition"] for r in rules]
        self.assertIn("arbre a chat xxl", conditions)
        self.assertIn("arbre chat grand", conditions)

    @patch("features.collections.injector.shopify_post")
    @patch("features.collections.injector.shopify_get")
    def test_skips_metafields_if_empty_meta(self, mock_get, mock_post):
        mock_post.return_value = {"smart_collection": {"id": 1}}
        mock_get.return_value  = {"metafields": []}

        create_collection(COL_CONFIG, "<p>desc</p>", "", "", BASE_URL, HEADERS)

        metafield_posts = [c for c in mock_post.call_args_list if "metafields" in c.args[0]]
        self.assertEqual(len(metafield_posts), 0)


# ── update_collection ─────────────────────────────────────────────────────────

class TestUpdateCollection(unittest.TestCase):

    @patch("features.collections.injector.shopify_put")
    @patch("features.collections.injector.shopify_post")
    @patch("features.collections.injector.shopify_get")
    def test_updates_body_html(self, mock_get, mock_post, mock_put):
        mock_put.return_value = {"smart_collection": {"id": 10}}
        mock_get.return_value = {"metafields": []}

        result = update_collection(10, "Col XXL", "<p>new desc</p>", "Title", "Desc", BASE_URL, HEADERS)

        self.assertEqual(result["id"], 10)
        put_payload = mock_put.call_args_list[0].args[2]
        self.assertEqual(put_payload["smart_collection"]["body_html"], "<p>new desc</p>")

    @patch("features.collections.injector.shopify_put")
    @patch("features.collections.injector.shopify_post")
    @patch("features.collections.injector.shopify_get")
    def test_updates_existing_title_tag_via_put(self, mock_get, mock_post, mock_put):
        mock_put.return_value = {"smart_collection": {"id": 10}}
        mock_get.return_value = {"metafields": [
            {"id": 99, "namespace": "global", "key": "title_tag", "value": "Old Title"}
        ]}

        update_collection(10, "Col", "<p>desc</p>", "New Title", "Desc", BASE_URL, HEADERS)

        # Le PUT metafield doit utiliser l'id existant
        metafield_puts = [c for c in mock_put.call_args_list if "metafields/99" in c.args[0]]
        self.assertEqual(len(metafield_puts), 1)

    @patch("features.collections.injector.shopify_put")
    @patch("features.collections.injector.shopify_post")
    @patch("features.collections.injector.shopify_get")
    def test_creates_new_title_tag_via_post(self, mock_get, mock_post, mock_put):
        mock_put.return_value = {"smart_collection": {"id": 10}}
        mock_get.return_value = {"metafields": []}

        update_collection(10, "Col", "<p>desc</p>", "New Title", "Desc", BASE_URL, HEADERS)

        metafield_posts = [c for c in mock_post.call_args_list if "metafields" in c.args[0]]
        self.assertGreater(len(metafield_posts), 0)

    @patch("features.collections.injector.shopify_put")
    def test_returns_none_on_exception(self, mock_put):
        mock_put.side_effect = Exception("Shopify error")
        result = update_collection(10, "Col", "<p>desc</p>", "T", "D", BASE_URL, HEADERS)
        self.assertIsNone(result)


# ── generate_injection_report ─────────────────────────────────────────────────

class TestGenerateInjectionReport(unittest.TestCase):

    def _make_log(self):
        return [
            {"nom": "Col A", "handle": "col-a", "action": "CRÉÉE",       "meta_title": "Titre A", "meta_desc": "Desc A", "statut": "OK",     "erreur": ""},
            {"nom": "Col B", "handle": "col-b", "action": "MISE À JOUR", "meta_title": "Titre B", "meta_desc": "Desc B", "statut": "ERREUR", "erreur": "Timeout"},
        ]

    def test_creates_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            self.assertTrue(os.path.exists(path))

    def test_filename_starts_with_collections_rapport(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
        self.assertTrue(os.path.basename(path).startswith("collections_rapport_"))
        self.assertTrue(path.endswith(".csv"))

    def test_csv_has_correct_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                fieldnames = csv.DictReader(f).fieldnames
        expected = ["date_heure", "nom", "handle", "action", "meta_title", "meta_desc_apercu", "statut", "erreur"]
        for col in expected:
            self.assertIn(col, fieldnames)

    def test_csv_has_correct_row_count(self):
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

    def test_meta_desc_truncated_to_80(self):
        log_entry = [{"nom": "Col", "handle": "col", "action": "CRÉÉE",
                      "meta_title": "T", "meta_desc": "X" * 200,
                      "statut": "OK", "erreur": ""}]
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(log_entry, tmp)
            with open(path, encoding="utf-8-sig") as f:
                row = list(csv.DictReader(f))[0]
        self.assertLessEqual(len(row["meta_desc_apercu"]), 80)

    def test_empty_log_creates_empty_csv(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report([], tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), 0)


if __name__ == "__main__":
    unittest.main()
