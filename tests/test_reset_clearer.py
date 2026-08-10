#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests — features/reset/clearer.py (retour en arrière Fiche Produit / Reviews)."""

import unittest
from unittest.mock import patch

from features.reset.clearer import clear_feature_metafields, FEATURE_METAFIELDS

BASE = "http://base"; H = {}


class TestClearFeatureMetafields(unittest.TestCase):
    def test_unknown_feature_raises(self):
        with self.assertRaises(ValueError):
            clear_feature_metafields("seo_boost", BASE, H)   # SEO Boost = snapshot, pas ici

    @patch("features.reset.clearer.delete_product_metafield")
    @patch("features.reset.clearer.fetch_all_product_metafields")
    @patch("features.reset.clearer.fetch_all_products")
    def test_deletes_only_feature_metafields(self, mock_products, mock_mf, mock_del):
        mock_products.return_value = [{"id": 1, "handle": "a"}]
        # metafields du produit : 2 de fiche_produit + 1 d'une autre feature (à NE PAS toucher)
        mock_mf.return_value = [
            {"id": 11, "namespace": "custom", "key": "phrase"},
            {"id": 12, "namespace": "custom", "key": "benefices"},
            {"id": 13, "namespace": "custom", "key": "caracteristique"},   # SEO → ignoré
            {"id": 14, "namespace": "global", "key": "title_tag"},         # SEO → ignoré
        ]
        res = clear_feature_metafields("fiche_produit", BASE, H)
        self.assertEqual(res["cleared"], 2)
        self.assertEqual(res["products"], 1)
        deleted_ids = sorted(c.args[0] for c in mock_del.call_args_list)
        self.assertEqual(deleted_ids, [11, 12])   # seulement phrase + benefices

    @patch("features.reset.clearer.delete_product_metafield")
    @patch("features.reset.clearer.fetch_all_product_metafields")
    @patch("features.reset.clearer.fetch_all_products")
    def test_reviews_clears_avis_slots_and_note(self, mock_products, mock_mf, mock_del):
        mock_products.return_value = [{"id": 1, "handle": "a"}]
        mock_mf.return_value = [
            {"id": 20, "namespace": "custom", "key": "avis_client_1"},
            {"id": 21, "namespace": "custom", "key": "avis_client_5"},
            {"id": 22, "namespace": "custom", "key": "note_globale"},
            {"id": 23, "namespace": "custom", "key": "phrase"},   # fiche → ignoré ici
        ]
        res = clear_feature_metafields("reviews", BASE, H)
        self.assertEqual(res["cleared"], 3)
        deleted = sorted(c.args[0] for c in mock_del.call_args_list)
        self.assertEqual(deleted, [20, 21, 22])

    @patch("features.reset.clearer.delete_product_metafield")
    @patch("features.reset.clearer.fetch_all_product_metafields")
    @patch("features.reset.clearer.fetch_all_products")
    def test_nothing_to_clear(self, mock_products, mock_mf, mock_del):
        mock_products.return_value = [{"id": 1, "handle": "a"}]
        mock_mf.return_value = [{"id": 30, "namespace": "custom", "key": "autre"}]
        res = clear_feature_metafields("reviews", BASE, H)
        self.assertEqual(res["cleared"], 0)
        self.assertEqual(res["products"], 0)
        mock_del.assert_not_called()

    def test_feature_metafields_keys(self):
        self.assertIn(("custom", "phrase"), FEATURE_METAFIELDS["fiche_produit"])
        self.assertIn(("custom", "avis_client_8"), FEATURE_METAFIELDS["reviews"])
        self.assertIn(("custom", "note_globale"), FEATURE_METAFIELDS["reviews"])


if __name__ == "__main__":
    unittest.main()
