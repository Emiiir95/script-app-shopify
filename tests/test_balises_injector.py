#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_balises_injector.py — Feature Balises : synchronisation des tags + lecture collections.

Le cœur testé est compute_synced_tags (mode synchronisation) : ajoute les tags des
collections choisies, retire ceux des collections non choisies, préserve tout le reste.
"""

import unittest
from unittest.mock import patch, MagicMock

from features.balises.injector import (
    normalize_tag,
    compute_synced_tags,
    fetch_collections_with_rules,
    update_product_tags,
)


def _col(handle, title, conditions):
    return {"handle": handle, "title": title, "conditions": conditions}


COLLECTIONS = [
    _col("doudou",  "Doudou",  ["doudou"]),
    _col("rose",    "Rose",    ["rose"]),
    _col("bleu",    "Bleu",    ["bleu"]),
    _col("musical", "Musical", ["musical"]),
]


class TestNormalizeTag(unittest.TestCase):
    def test_accents_case_dashes(self):
        self.assertEqual(normalize_tag("Doudou-Rosé"), "doudou rose")

    def test_empty(self):
        self.assertEqual(normalize_tag(""), "")


class TestComputeSyncedTags(unittest.TestCase):
    """Mode REMISE À PLAT : le produit ne garde QUE les tags des collections choisies."""

    def _final(self, r):
        return sorted(normalize_tag(t) for t in r["new_tags"])

    def test_adds_chosen_collection_tags(self):
        r = compute_synced_tags("", COLLECTIONS, ["doudou"])
        self.assertEqual(self._final(r), ["doudou"])
        self.assertEqual(r["added"], ["doudou"])
        self.assertEqual(r["removed"], [])
        self.assertTrue(r["changed"])

    def test_wipes_non_collection_tags(self):
        # promo/seo ne sont dans AUCUNE collection → supprimés en remise à plat.
        r = compute_synced_tags("doudou, rose, promo, seo-lapin", COLLECTIONS, ["doudou"])
        self.assertEqual(self._final(r), ["doudou"])
        removed = sorted(normalize_tag(t) for t in r["removed"])
        self.assertEqual(removed, ["promo", "rose", "seo lapin"])

    def test_removes_unchosen_collection_tag(self):
        r = compute_synced_tags("doudou, rose", COLLECTIONS, ["doudou"])
        self.assertEqual(self._final(r), ["doudou"])
        self.assertEqual([normalize_tag(t) for t in r["removed"]], ["rose"])

    def test_idempotent_when_exactly_chosen(self):
        r = compute_synced_tags("doudou, bleu", COLLECTIONS, ["doudou", "bleu"])
        self.assertFalse(r["changed"])
        self.assertEqual(r["added"], [])
        self.assertEqual(r["removed"], [])

    def test_extra_tag_makes_it_change(self):
        # Même collections choisies, mais un tag en trop → doit être retiré.
        r = compute_synced_tags("doudou, promo", COLLECTIONS, ["doudou"])
        self.assertTrue(r["changed"])
        self.assertEqual(self._final(r), ["doudou"])
        self.assertEqual([normalize_tag(t) for t in r["removed"]], ["promo"])

    def test_full_reclassification(self):
        r = compute_synced_tags("rose, musical, seo", COLLECTIONS, ["doudou", "bleu"])
        self.assertEqual(self._final(r), ["bleu", "doudou"])
        self.assertEqual(sorted(normalize_tag(t) for t in r["removed"]),
                         ["musical", "rose", "seo"])

    def test_empty_chosen_wipes_everything(self):
        r = compute_synced_tags("doudou, rose, garde-moi", COLLECTIONS, [])
        self.assertEqual(r["new_tags"], [])
        self.assertTrue(r["changed"])

    def test_list_input_accepted(self):
        r = compute_synced_tags(["doudou", "rose"], COLLECTIONS, ["doudou"])
        self.assertEqual(self._final(r), ["doudou"])

    def test_collection_without_conditions_is_ignored(self):
        cols = COLLECTIONS + [_col("manuelle", "Manuelle", [])]
        r = compute_synced_tags("", cols, ["manuelle"])
        self.assertEqual(r["new_tags"], [])
        self.assertFalse(r["changed"])

    def test_deduplicates_chosen(self):
        r = compute_synced_tags("", COLLECTIONS, ["doudou", "doudou"])
        norms = [normalize_tag(t) for t in r["new_tags"]]
        self.assertEqual(norms.count("doudou"), 1)


class TestFetchCollectionsWithRules(unittest.TestCase):
    @patch("features.balises.injector.shopify_get")
    def test_extracts_tag_conditions(self, mock_get):
        mock_get.return_value = {
            "smart_collections": [
                {"id": 1, "handle": "doudou", "title": "Doudou", "body_html": "<p>desc</p>",
                 "rules": [{"column": "tag", "relation": "equals", "condition": "doudou"}]},
                {"id": 2, "handle": "prix", "title": "Prix", "body_html": "",
                 "rules": [{"column": "variant_price", "relation": "less_than", "condition": "50"}]},
            ]
        }
        cols = fetch_collections_with_rules("http://x", {})
        self.assertEqual(cols[0]["conditions"], ["doudou"])
        self.assertEqual(cols[0]["description"], "<p>desc</p>")
        self.assertEqual(cols[1]["conditions"], [])   # règle non-tag → intaggable

    @patch("features.balises.injector.shopify_put")
    def test_update_product_tags_puts_csv(self, mock_put):
        csv = update_product_tags(123, ["doudou", "bleu"], "http://x", {})
        self.assertEqual(csv, "doudou, bleu")
        args = mock_put.call_args[0]
        self.assertEqual(args[2]["product"]["tags"], "doudou, bleu")
        self.assertEqual(args[2]["product"]["id"], 123)


if __name__ == "__main__":
    unittest.main()
