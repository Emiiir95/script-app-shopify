"""
Tests unitaires — features/fond_studio/injector.py

Couvre : add_first_image, generate_injection_report
"""
import base64
import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from features.fond_studio.injector import add_first_image, generate_injection_report


class TestAddFirstImage(unittest.TestCase):
    @patch("features.fond_studio.injector.shopify_post")
    def test_builds_position_1_payload(self, mock_post):
        mock_post.return_value = {"image": {"id": 999, "position": 1}}

        img = add_first_image(101, b"PNGDATA", "Mon Produit", "http://base", {})

        url, headers, payload = mock_post.call_args[0]
        self.assertIn("/products/101/images.json", url)
        self.assertEqual(payload["image"]["position"], 1)
        self.assertEqual(payload["image"]["alt"], "Mon Produit")
        # attachment = base64 des bytes
        self.assertEqual(payload["image"]["attachment"], base64.b64encode(b"PNGDATA").decode("ascii"))
        self.assertEqual(img["id"], 999)

    @patch("features.fond_studio.injector.shopify_post")
    def test_empty_alt_defaults_to_empty_string(self, mock_post):
        mock_post.return_value = {"image": {"id": 1}}
        add_first_image(1, b"x", None, "http://base", {})
        _, _, payload = mock_post.call_args[0]
        self.assertEqual(payload["image"]["alt"], "")


class TestGenerateInjectionReport(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_creates_csv_in_rapports(self):
        rows = [{"handle": "a", "product_id": 1, "new_image_id": 99, "statut": "OK", "erreur": ""}]
        path = generate_injection_report(rows, self.tmpdir)
        self.assertTrue(os.path.exists(path))
        self.assertIn("rapports", path)

    def test_content_matches(self):
        rows = [
            {"handle": "a", "product_id": 1, "new_image_id": 99, "statut": "OK", "erreur": ""},
            {"handle": "b", "product_id": 2, "new_image_id": "", "statut": "ERREUR", "erreur": "boom"},
        ]
        path = generate_injection_report(rows, self.tmpdir)
        with open(path, encoding="utf-8-sig") as f:
            read = list(csv.DictReader(f))
        self.assertEqual(len(read), 2)
        self.assertEqual(read[0]["handle"], "a")
        self.assertEqual(read[1]["statut"], "ERREUR")
        self.assertEqual(read[1]["erreur"], "boom")


if __name__ == "__main__":
    unittest.main()
