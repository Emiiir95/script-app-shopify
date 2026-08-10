#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests — utils/archive.py (archive permanente de la data générée)."""

import os
import tempfile
import unittest

from utils.archive import save_generated, list_generated, latest_generated, ARCHIVE_DIRNAME


class TestArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_save_creates_file_in_generated_dir(self):
        path = save_generated(self.tmp, "seo_boost", [{"product": {"id": 1}}], "x.myshopify.com")
        self.assertTrue(os.path.isfile(path))
        self.assertIn(ARCHIVE_DIRNAME, path)

    def test_latest_returns_products_data(self):
        save_generated(self.tmp, "seo_boost", [{"product": {"id": 1}, "seo_data": {"h1": "A"}}])
        arch = latest_generated(self.tmp, "seo_boost")
        self.assertEqual(arch["feature"], "seo_boost")
        self.assertEqual(arch["products_data"][0]["seo_data"]["h1"], "A")

    def test_list_filters_by_feature(self):
        # noms horodatés distincts via écriture manuelle (même seconde possible)
        d = os.path.join(self.tmp, ARCHIVE_DIRNAME); os.makedirs(d)
        for n in ["seo_boost_2026-08-01_10-00-00.json", "reviews_2026-08-02_10-00-00.json"]:
            open(os.path.join(d, n), "w").write("{}")
        self.assertEqual(list_generated(self.tmp, "reviews"), ["reviews_2026-08-02_10-00-00.json"])
        self.assertEqual(len(list_generated(self.tmp)), 2)

    def test_latest_none_when_absent(self):
        self.assertIsNone(latest_generated(self.tmp, "seo_boost"))


if __name__ == "__main__":
    unittest.main()
