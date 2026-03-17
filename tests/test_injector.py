"""
Tests unitaires — features/reviews/injector.py

Couvre : generate_csv_preview, inject_product_reviews
"""
import csv
import os
import tempfile
import unittest
from unittest.mock import patch, MagicMock

from features.reviews.injector import generate_csv_preview, inject_product_reviews


SAMPLE_PRODUCTS_DATA = [
    {
        "handle":      "prod-a",
        "rating":      4.8,
        "count":       250,
        "note_globale": "<strong>4.8</strong> | 250+ avis vérifiés",
        "reviews": [
            {"titre": "Super",   "texte": "Excellent produit",  "nom_auteur": "Jean D.",  "note": "4.8"},
            {"titre": "Top",     "texte": "Je recommande",      "nom_auteur": "Marie L.", "note": "5.0"},
        ],
        "missing_slots": [1, 2],
    }
]


class TestGenerateCsvPreview(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _read_csv(self):
        with open(os.path.join(self.tmpdir, "reviews_preview.csv"), encoding="utf-8") as f:
            return list(csv.DictReader(f))

    def test_creates_csv_file_in_store_path(self):
        generate_csv_preview(SAMPLE_PRODUCTS_DATA, self.tmpdir)
        self.assertTrue(os.path.exists(os.path.join(self.tmpdir, "reviews_preview.csv")))

    def test_csv_has_handle_rating_count_columns(self):
        generate_csv_preview(SAMPLE_PRODUCTS_DATA, self.tmpdir)
        rows = self._read_csv()
        self.assertIn("handle", rows[0])
        self.assertIn("rating_global", rows[0])
        self.assertIn("review_count", rows[0])

    def test_csv_has_8_review_slots(self):
        generate_csv_preview(SAMPLE_PRODUCTS_DATA, self.tmpdir)
        rows = self._read_csv()
        for i in range(1, 9):
            self.assertIn(f"review{i}_title", rows[0])
            self.assertIn(f"review{i}_text", rows[0])
            self.assertIn(f"review{i}_author", rows[0])
            self.assertIn(f"review{i}_rating", rows[0])

    def test_csv_contains_correct_product_data(self):
        generate_csv_preview(SAMPLE_PRODUCTS_DATA, self.tmpdir)
        rows = self._read_csv()
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["handle"], "prod-a")
        self.assertEqual(rows[0]["rating_global"], "4.8")
        self.assertEqual(rows[0]["review_count"], "250")

    def test_csv_contains_correct_review_data(self):
        generate_csv_preview(SAMPLE_PRODUCTS_DATA, self.tmpdir)
        rows = self._read_csv()
        self.assertEqual(rows[0]["review1_title"], "Super")
        self.assertEqual(rows[0]["review1_author"], "Jean D.")
        self.assertEqual(rows[0]["review2_title"], "Top")
        self.assertEqual(rows[0]["review2_author"], "Marie L.")

    def test_csv_has_one_row_per_product(self):
        two_products = SAMPLE_PRODUCTS_DATA + [
            {
                "handle": "prod-b", "rating": 4.9, "count": 100,
                "note_globale": "<strong>4.9</strong> | 100+ avis vérifiés",
                "reviews": [{"titre": "Bien", "texte": "OK", "nom_auteur": "Paul B.", "note": "4.9"}],
                "missing_slots": [1],
            }
        ]
        generate_csv_preview(two_products, self.tmpdir)
        rows = self._read_csv()
        self.assertEqual(len(rows), 2)


class TestInjectProductReviews(unittest.TestCase):
    PRODUCT = {"id": 101, "handle": "prod-a"}
    REVIEWS_DATA = {
        "note_globale":  "<strong>4.8</strong> | 250+ avis vérifiés",
        "reviews": [
            {"note": "4.8", "titre": "Super", "texte": "...", "nom_auteur": "Jean D."},
            {"note": "5.0", "titre": "Top",   "texte": "...", "nom_auteur": "Marie L."},
        ],
        "missing_slots": [1, 2],
    }

    @patch("features.reviews.injector.time.sleep")
    @patch("features.reviews.injector.set_product_metafield")
    @patch("features.reviews.injector.create_metaobject")
    def test_creates_one_metaobject_per_review(self, mock_create, mock_set, mock_sleep):
        mock_create.side_effect = ["gid://1", "gid://2"]

        inject_product_reviews(self.PRODUCT, self.REVIEWS_DATA, "http://base", {})

        self.assertEqual(mock_create.call_count, 2)

    @patch("features.reviews.injector.time.sleep")
    @patch("features.reviews.injector.set_product_metafield")
    @patch("features.reviews.injector.create_metaobject")
    def test_sets_correct_metafield_slots(self, mock_create, mock_set, mock_sleep):
        mock_create.side_effect = ["gid://1", "gid://2"]

        inject_product_reviews(self.PRODUCT, self.REVIEWS_DATA, "http://base", {})

        set_keys = [c[0][2] for c in mock_set.call_args_list]  # 3ème arg = key
        self.assertIn("avis_clients_1", set_keys)
        self.assertIn("avis_clients_2", set_keys)

    @patch("features.reviews.injector.time.sleep")
    @patch("features.reviews.injector.set_product_metafield")
    @patch("features.reviews.injector.create_metaobject")
    def test_sets_note_globale_metafield(self, mock_create, mock_set, mock_sleep):
        mock_create.side_effect = ["gid://1", "gid://2"]

        inject_product_reviews(self.PRODUCT, self.REVIEWS_DATA, "http://base", {})

        set_keys = [c[0][2] for c in mock_set.call_args_list]
        self.assertIn("note_globale_du_produit", set_keys)

    @patch("features.reviews.injector.time.sleep")
    @patch("features.reviews.injector.set_product_metafield")
    @patch("features.reviews.injector.create_metaobject")
    def test_total_metafield_calls(self, mock_create, mock_set, mock_sleep):
        """2 avis_clients + 1 note_globale = 3 appels set_product_metafield."""
        mock_create.side_effect = ["gid://1", "gid://2"]

        inject_product_reviews(self.PRODUCT, self.REVIEWS_DATA, "http://base", {})

        self.assertEqual(mock_set.call_count, 3)

    @patch("features.reviews.injector.time.sleep")
    @patch("features.reviews.injector.set_product_metafield")
    @patch("features.reviews.injector.create_metaobject")
    def test_uses_gids_from_metaobject_creation(self, mock_create, mock_set, mock_sleep):
        mock_create.side_effect = ["gid://shopify/Metaobject/1", "gid://shopify/Metaobject/2"]

        inject_product_reviews(self.PRODUCT, self.REVIEWS_DATA, "http://base", {})

        set_values = [c[0][3] for c in mock_set.call_args_list]  # 4ème arg = value
        self.assertIn("gid://shopify/Metaobject/1", set_values)
        self.assertIn("gid://shopify/Metaobject/2", set_values)


if __name__ == "__main__":
    unittest.main()
