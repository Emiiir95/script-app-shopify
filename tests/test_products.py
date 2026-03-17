"""
Tests unitaires — shopify/products.py

Couvre : fetch_all_products, fetch_product_metafields,
         missing_review_slots, set_product_metafield
"""
import unittest
from unittest.mock import patch, MagicMock

from shopify.products import (
    fetch_all_products,
    fetch_product_metafields,
    missing_review_slots,
    set_product_metafield,
)


class TestFetchAllProducts(unittest.TestCase):
    @patch("shopify.products.shopify_get_paginated")
    def test_single_page(self, mock_get):
        mock_get.return_value = (
            {"products": [{"id": 1, "handle": "prod-a", "title": "Prod A"}]},
            "",
        )
        products = fetch_all_products("http://base", {})
        self.assertEqual(len(products), 1)
        self.assertEqual(products[0]["id"], 1)

    @patch("shopify.products.shopify_get_paginated")
    def test_pagination_two_pages(self, mock_get):
        mock_get.side_effect = [
            (
                {"products": [{"id": 1}]},
                '<https://example.com/products.json?page_info=abc>; rel="next"',
            ),
            (
                {"products": [{"id": 2}]},
                "",
            ),
        ]
        products = fetch_all_products("http://base", {})
        self.assertEqual(len(products), 2)
        self.assertEqual(products[0]["id"], 1)
        self.assertEqual(products[1]["id"], 2)

    @patch("shopify.products.shopify_get_paginated")
    def test_empty_store(self, mock_get):
        mock_get.return_value = ({"products": []}, "")
        products = fetch_all_products("http://base", {})
        self.assertEqual(products, [])

    @patch("shopify.products.shopify_get_paginated")
    def test_uses_next_url_without_original_params(self, mock_get):
        """La deuxième page doit utiliser l'URL 'next' sans les params initiaux."""
        mock_get.side_effect = [
            ({"products": [{"id": 1}]}, '<https://example.com/page2>; rel="next"'),
            ({"products": []}, ""),
        ]
        fetch_all_products("http://base", {})
        second_call = mock_get.call_args_list[1]
        second_call_url = second_call[0][0]
        self.assertEqual(second_call_url, "https://example.com/page2")
        # params est passé en keyword arg : call(url, headers, params=None)
        second_call_params = second_call[1].get("params")
        self.assertIsNone(second_call_params)


class TestFetchProductMetafields(unittest.TestCase):
    @patch("shopify.products.shopify_get")
    def test_filters_custom_namespace_only(self, mock_get):
        mock_get.return_value = {
            "metafields": [
                {"namespace": "custom", "key": "avis_client_1", "value": "gid://1"},
                {"namespace": "seo",    "key": "title",          "value": "SEO title"},
            ]
        }
        result = fetch_product_metafields(123, "http://base", {})
        self.assertIn("avis_client_1", result)
        self.assertEqual(result["avis_client_1"], "gid://1")
        self.assertNotIn("title", result)

    @patch("shopify.products.shopify_get")
    def test_empty_metafields(self, mock_get):
        mock_get.return_value = {"metafields": []}
        result = fetch_product_metafields(123, "http://base", {})
        self.assertEqual(result, {})

    @patch("shopify.products.shopify_get")
    def test_multiple_custom_metafields(self, mock_get):
        mock_get.return_value = {
            "metafields": [
                {"namespace": "custom", "key": "avis_client_1", "value": "gid://1"},
                {"namespace": "custom", "key": "avis_client_2", "value": "gid://2"},
                {"namespace": "custom", "key": "note_globale_du_produit", "value": "4.8"},
            ]
        }
        result = fetch_product_metafields(1, "http://base", {})
        self.assertEqual(len(result), 3)


class TestMissingReviewSlots(unittest.TestCase):
    def test_all_missing_when_empty(self):
        missing = missing_review_slots({})
        self.assertEqual(missing, [1, 2, 3, 4, 5, 6, 7, 8])

    def test_some_slots_filled(self):
        metafields = {"avis_client_1": "gid://1", "avis_client_3": "gid://3"}
        missing = missing_review_slots(metafields)
        self.assertEqual(missing, [2, 4, 5, 6, 7, 8])

    def test_all_filled(self):
        metafields = {f"avis_client_{i}": f"gid://{i}" for i in range(1, 9)}
        missing = missing_review_slots(metafields)
        self.assertEqual(missing, [])

    def test_empty_string_value_counts_as_missing(self):
        metafields = {"avis_client_1": ""}
        missing = missing_review_slots(metafields)
        self.assertIn(1, missing)

    def test_only_first_slot_filled(self):
        metafields = {"avis_client_1": "gid://1"}
        missing = missing_review_slots(metafields)
        self.assertEqual(missing, [2, 3, 4, 5, 6, 7, 8])


class TestSetProductMetafield(unittest.TestCase):
    @patch("shopify.products.shopify_put")
    @patch("shopify.products.shopify_get")
    def test_updates_existing_metafield_via_put(self, mock_get, mock_put):
        mock_get.return_value = {
            "metafields": [
                {"namespace": "custom", "key": "note_globale_du_produit", "id": 999, "value": "old"}
            ]
        }
        set_product_metafield(1, "custom", "note_globale_du_produit", "new_val", "single_line_text_field", "http://base", {})

        mock_put.assert_called_once()
        put_url = mock_put.call_args[0][0]
        self.assertIn("999", put_url)
        mock_put.assert_called_once()

    @patch("shopify.products.shopify_post")
    @patch("shopify.products.shopify_get")
    def test_creates_new_metafield_via_post(self, mock_get, mock_post):
        mock_get.return_value = {"metafields": []}
        set_product_metafield(42, "custom", "avis_client_1", "gid://x", "metaobject_reference", "http://base", {})

        mock_post.assert_called_once()
        post_url = mock_post.call_args[0][0]
        self.assertIn("42", post_url)

    @patch("shopify.products.shopify_post")
    @patch("shopify.products.shopify_get")
    def test_payload_contains_correct_fields(self, mock_get, mock_post):
        mock_get.return_value = {"metafields": []}
        set_product_metafield(1, "custom", "avis_client_1", "gid://1", "metaobject_reference", "http://base", {})

        payload = mock_post.call_args[0][2]
        mf = payload["metafield"]
        self.assertEqual(mf["namespace"], "custom")
        self.assertEqual(mf["key"], "avis_client_1")
        self.assertEqual(mf["value"], "gid://1")
        self.assertEqual(mf["type"], "metaobject_reference")


if __name__ == "__main__":
    unittest.main()
