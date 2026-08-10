#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_seo_boost_supplier.py — Tests de la préservation de la description
fournisseur (features/seo_boost/runner.resolve_supplier_description).

Garantit qu'on régénère depuis la source d'origine et jamais par-dessus le
contenu déjà généré : au 1er passage, body_html est sauvegardé dans un metafield ;
aux passages suivants, c'est ce metafield qui sert de source.
"""

import unittest
from unittest.mock import patch

from features.seo_boost.runner import (
    resolve_supplier_description,
    SUPPLIER_DESC_KEY,
)

BASE_URL = "https://x.myshopify.com/admin/api/2026-01"
HEADERS  = {"X-Shopify-Access-Token": "shpat_test"}
PRODUCT  = {"id": 123, "handle": "mon-produit", "body_html": "<p>Description fournisseur d'origine</p>"}


class TestResolveSupplierDescription(unittest.TestCase):

    @patch("features.seo_boost.runner.set_product_metafield")
    @patch("features.seo_boost.runner.fetch_product_metafields")
    def test_uses_backup_when_present(self, mock_fetch, mock_set):
        # Un backup existe → on l'utilise, on ne ré-écrit PAS le metafield
        mock_fetch.return_value = {SUPPLIER_DESC_KEY: "<p>Vraie source fournisseur</p>"}
        result = resolve_supplier_description(PRODUCT, BASE_URL, HEADERS)
        self.assertIn("Vraie source fournisseur", result)
        mock_set.assert_not_called()

    @patch("features.seo_boost.runner.set_product_metafield")
    @patch("features.seo_boost.runner.fetch_product_metafields")
    def test_backs_up_body_html_on_first_pass(self, mock_fetch, mock_set):
        # Aucun backup → on sauvegarde le body_html actuel puis on l'utilise
        mock_fetch.return_value = {}
        result = resolve_supplier_description(PRODUCT, BASE_URL, HEADERS)
        self.assertIn("Description fournisseur d'origine", result)
        mock_set.assert_called_once()
        args = mock_set.call_args.args
        self.assertEqual(args[0], 123)                 # product_id
        self.assertEqual(args[1], "custom")            # namespace
        self.assertEqual(args[2], SUPPLIER_DESC_KEY)   # key
        self.assertEqual(args[3], PRODUCT["body_html"])  # value = html d'origine

    @patch("features.seo_boost.runner.set_product_metafield")
    @patch("features.seo_boost.runner.fetch_product_metafields")
    def test_empty_body_html_no_save(self, mock_fetch, mock_set):
        mock_fetch.return_value = {}
        result = resolve_supplier_description(
            {"id": 1, "handle": "h", "body_html": ""}, BASE_URL, HEADERS)
        self.assertEqual(result, "")
        mock_set.assert_not_called()

    @patch("features.seo_boost.runner.set_product_metafield")
    @patch("features.seo_boost.runner.fetch_product_metafields")
    def test_blank_backup_falls_back_to_body_html(self, mock_fetch, mock_set):
        # Backup présent mais vide → traité comme absent, on sauvegarde body_html
        mock_fetch.return_value = {SUPPLIER_DESC_KEY: "   "}
        result = resolve_supplier_description(PRODUCT, BASE_URL, HEADERS)
        self.assertIn("Description fournisseur d'origine", result)
        mock_set.assert_called_once()

    @patch("features.seo_boost.runner.set_product_metafield")
    @patch("features.seo_boost.runner.fetch_product_metafields")
    def test_fetch_failure_falls_back_to_body_html(self, mock_fetch, mock_set):
        # Échec de lecture des metafields → repli sur body_html, pas de crash
        mock_fetch.side_effect = Exception("network down")
        result = resolve_supplier_description(PRODUCT, BASE_URL, HEADERS)
        self.assertIn("Description fournisseur d'origine", result)
        mock_set.assert_not_called()


if __name__ == "__main__":
    unittest.main()
