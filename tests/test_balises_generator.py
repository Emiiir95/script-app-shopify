#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_balises_generator.py — Feature Balises : classement IA (classify_product).

OpenAI est mocké. On vérifie : validation des handles, respect du plafond, repli.
"""

import json
import unittest
from unittest.mock import MagicMock

from features.balises.generator import classify_product


class _Usage:
    prompt_tokens = 1
    completion_tokens = 1
    total_tokens = 2


def _client(content=None, raise_exc=False):
    client = MagicMock()
    if raise_exc:
        client.chat.completions.create.side_effect = Exception("boom")
    else:
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content=content))]
        resp.usage = _Usage()
        client.chat.completions.create.return_value = resp
    return client


COLS = [
    {"handle": "doudou", "title": "Doudou", "description": ""},
    {"handle": "rose",   "title": "Rose",   "description": ""},
    {"handle": "bleu",   "title": "Bleu",   "description": ""},
]
CTX = {"title": "Doudou Lapin Rose", "description": "doux", "product_type": "",
       "caracteristiques": "", "tags": ""}


class TestClassifyProduct(unittest.TestCase):
    def test_returns_valid_handles(self):
        c = _client(json.dumps({"collections": ["doudou", "rose"]}))
        self.assertEqual(classify_product(CTX, COLS, c, MagicMock()), ["doudou", "rose"])

    def test_filters_out_invalid_handles(self):
        c = _client(json.dumps({"collections": ["doudou", "inexistant"]}))
        self.assertEqual(classify_product(CTX, COLS, c, MagicMock()), ["doudou"])

    def test_deduplicates(self):
        c = _client(json.dumps({"collections": ["rose", "rose", "doudou"]}))
        self.assertEqual(classify_product(CTX, COLS, c, MagicMock()), ["rose", "doudou"])

    def test_respects_max_collections(self):
        c = _client(json.dumps({"collections": ["doudou", "rose", "bleu"]}))
        out = classify_product(CTX, COLS, c, MagicMock(), max_collections=2)
        self.assertEqual(out, ["doudou", "rose"])

    def test_no_cap_when_zero(self):
        c = _client(json.dumps({"collections": ["doudou", "rose", "bleu"]}))
        out = classify_product(CTX, COLS, c, MagicMock(), max_collections=0)
        self.assertEqual(out, ["doudou", "rose", "bleu"])

    def test_empty_collections_returns_empty_without_call(self):
        c = _client(json.dumps({"collections": []}))
        self.assertEqual(classify_product(CTX, [], c, MagicMock()), [])
        c.chat.completions.create.assert_not_called()

    def test_returns_none_on_ai_failure(self):
        # Échec réseau/parse → None (≠ liste vide) pour que le runner saute le produit.
        c = _client(raise_exc=True)
        self.assertIsNone(classify_product(CTX, COLS, c, MagicMock(), max_retries=2))

    def test_missing_key_returns_empty_list(self):
        # Réponse valide mais sans "collections" → liste vide légitime (pas un échec).
        c = _client(json.dumps({}))
        self.assertEqual(classify_product(CTX, COLS, c, MagicMock()), [])


if __name__ == "__main__":
    unittest.main()
