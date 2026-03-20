#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_normalisation.py — Tests unitaires pour features/normalisation/

Couvre :
  - compute_variant_changes  : logique prix + détection changements
  - normalize_product        : PUT produit + PUT variantes
  - generate_injection_report: création CSV post-injection
"""

import csv
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

from features.normalisation.injector import (
    compute_variant_changes,
    normalize_product,
    generate_injection_report,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _variant(price, compare_at=None, taxable=False, inv_policy="deny",
             fulfillment="manual", requires_shipping=True, sku="SKU1", vid=101):
    return {
        "id":                   vid,
        "sku":                  sku,
        "price":                str(price),
        "compare_at_price":     str(compare_at) if compare_at is not None else None,
        "taxable":              taxable,
        "inventory_policy":     inv_policy,
        "fulfillment_service":  fulfillment,
        "requires_shipping":    requires_shipping,
    }


def _product(pid=1, handle="test-handle", title="Test", status="active", variants=None):
    return {
        "id":       pid,
        "handle":   handle,
        "title":    title,
        "status":   status,
        "variants": variants or [_variant(29.99)],
    }


BASE_URL = "https://test.myshopify.com/admin/api/2026-01"
HEADERS  = {"X-Shopify-Access-Token": "test"}


# ── compute_variant_changes ───────────────────────────────────────────────────

class TestComputeVariantChanges(unittest.TestCase):

    def test_compare_at_higher_sets_new_price(self):
        v = _variant(price=29.99, compare_at=49.99)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "49.99")

    def test_compare_at_lower_keeps_price(self):
        v = _variant(price=59.99, compare_at=39.99)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "59.99")

    def test_no_compare_at_keeps_price(self):
        v = _variant(price=39.99, compare_at=None)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "39.99")

    def test_equal_prices_keeps_price(self):
        v = _variant(price=30.00, compare_at=30.00)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "30.00")

    def test_changed_false_when_already_normalized(self):
        v = _variant(price=39.99, compare_at=None, taxable=False,
                     inv_policy="deny", fulfillment="manual", requires_shipping=True)
        c = compute_variant_changes(v)
        self.assertFalse(c["changed"])

    def test_changed_true_when_compare_at_nonzero(self):
        # compare_at non vide → doit être vidé → changed=True
        v = _variant(price=39.99, compare_at=39.99)
        c = compute_variant_changes(v)
        self.assertTrue(c["changed"])

    def test_changed_true_when_taxable_true(self):
        v = _variant(price=39.99, compare_at=None, taxable=True)
        c = compute_variant_changes(v)
        self.assertTrue(c["changed"])

    def test_changed_true_when_inventory_policy_wrong(self):
        v = _variant(price=39.99, compare_at=None, inv_policy="continue")
        c = compute_variant_changes(v)
        self.assertTrue(c["changed"])

    def test_changed_true_when_fulfillment_wrong(self):
        v = _variant(price=39.99, compare_at=None, fulfillment="gift_card")
        c = compute_variant_changes(v)
        self.assertTrue(c["changed"])

    def test_prix_avant_preserved(self):
        v = _variant(price=29.99, compare_at=49.99)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_avant"], "29.99")
        self.assertEqual(c["compare_at_avant"], "49.99")

    def test_invalid_price_does_not_raise(self):
        v = _variant(price="", compare_at=None)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "0.00")


# ── normalize_product ─────────────────────────────────────────────────────────

class TestNormalizeProduct(unittest.TestCase):

    @patch("features.normalisation.injector.shopify_put")
    def test_puts_each_variant(self, mock_put):
        mock_put.return_value = {}
        variants = [_variant(29.99, vid=101, sku="A"), _variant(39.99, vid=102, sku="B")]
        product  = _product(pid=1, status="active", variants=variants)

        normalize_product(product, BASE_URL, HEADERS)

        # 2 PUT variantes (pas de PUT produit car status déjà active)
        self.assertEqual(mock_put.call_count, 2)
        urls = [c.args[0] for c in mock_put.call_args_list]
        self.assertIn(f"{BASE_URL}/variants/101.json", urls)
        self.assertIn(f"{BASE_URL}/variants/102.json", urls)

    @patch("features.normalisation.injector.shopify_put")
    def test_puts_product_when_status_not_active(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=5, status="draft", variants=[_variant(10.00, vid=200)])

        normalize_product(product, BASE_URL, HEADERS)

        # 1 PUT produit + 1 PUT variante = 2 calls total
        self.assertEqual(mock_put.call_count, 2)
        product_url = f"{BASE_URL}/products/5.json"
        urls = [c.args[0] for c in mock_put.call_args_list]
        self.assertIn(product_url, urls)

    @patch("features.normalisation.injector.shopify_put")
    def test_variant_payload_has_correct_fields(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=1, status="active", variants=[_variant(29.99, compare_at=49.99, vid=101)])

        normalize_product(product, BASE_URL, HEADERS)

        variant_call = next(
            c for c in mock_put.call_args_list
            if "variants" in c.args[0]
        )
        payload = variant_call.args[2]["variant"]
        self.assertEqual(payload["price"], "49.99")
        self.assertIsNone(payload["compare_at_price"])
        self.assertFalse(payload["taxable"])
        self.assertEqual(payload["inventory_policy"], "deny")
        self.assertEqual(payload["fulfillment_service"], "manual")
        self.assertTrue(payload["requires_shipping"])

    @patch("features.normalisation.injector.shopify_put")
    def test_returns_one_entry_per_variant(self, mock_put):
        mock_put.return_value = {}
        variants = [_variant(10.00, vid=1), _variant(20.00, vid=2), _variant(30.00, vid=3)]
        product  = _product(status="active", variants=variants)

        results = normalize_product(product, BASE_URL, HEADERS)
        self.assertEqual(len(results), 3)

    @patch("features.normalisation.injector.shopify_put")
    def test_skips_product_put_when_already_active(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=9, status="active", variants=[_variant(10.00, vid=99)])

        normalize_product(product, BASE_URL, HEADERS)

        urls = [c.args[0] for c in mock_put.call_args_list]
        self.assertNotIn(f"{BASE_URL}/products/9.json", urls)


# ── generate_injection_report ─────────────────────────────────────────────────

class TestGenerateInjectionReport(unittest.TestCase):

    def _make_log(self):
        return [
            {"handle": "prod-1", "titre_produit": "Produit 1", "sku": "A",
             "prix_avant": "29.99", "compare_at_avant": "49.99", "prix_apres": "49.99",
             "statut": "OK", "erreur": ""},
            {"handle": "prod-2", "titre_produit": "Produit 2", "sku": "B",
             "prix_avant": "59.99", "compare_at_avant": "", "prix_apres": "59.99",
             "statut": "ERREUR", "erreur": "Timeout"},
        ]

    def test_creates_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            self.assertTrue(os.path.exists(path))

    def test_csv_has_correct_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
            expected = ["date_heure", "handle", "titre_produit", "sku",
                        "prix_avant", "compare_at_avant", "prix_apres", "statut", "erreur"]
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
                rows = list(csv.DictReader(f))
            statuts = [r["statut"] for r in rows]
            self.assertIn("OK", statuts)
            self.assertIn("ERREUR", statuts)

    def test_filename_contains_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            filename = os.path.basename(path)
            self.assertTrue(filename.startswith("normalisation_rapport_"))
            self.assertTrue(filename.endswith(".csv"))

    def test_prix_apres_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["prix_apres"], "49.99")


if __name__ == "__main__":
    unittest.main()
