#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests unitaires — utils/backup.py (snapshots produits pour retour en arrière)."""

import json
import os
import tempfile
import unittest

from utils.backup import (
    save_snapshot, list_snapshots, latest_snapshot_file, load_snapshot,
    BACKUPS_DIRNAME,
)

PRODUCTS = [
    {"id": 1, "title": "A", "handle": "a", "body_html": "<p>A</p>", "extra": "ignore"},
    {"id": 2, "title": "B", "handle": "b", "body_html": "<p>B</p>"},
    {"title": "no-id", "handle": "x"},   # sans id → ignoré
]
FIELDS = ["title", "handle", "body_html"]


class TestSaveSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def test_creates_file_in_backups_dir(self):
        path = save_snapshot(self.tmp, "seo_boost", PRODUCTS, FIELDS)
        self.assertTrue(os.path.isfile(path))
        self.assertIn(BACKUPS_DIRNAME, path)

    def test_only_products_with_id_saved(self):
        path = save_snapshot(self.tmp, "seo_boost", PRODUCTS, FIELDS)
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
        self.assertEqual(len(snap["products"]), 2)
        self.assertEqual({p["id"] for p in snap["products"]}, {1, 2})

    def test_saves_only_requested_fields(self):
        path = save_snapshot(self.tmp, "seo_boost", PRODUCTS, FIELDS)
        with open(path, encoding="utf-8") as f:
            snap = json.load(f)
        p1 = next(p for p in snap["products"] if p["id"] == 1)
        self.assertEqual(p1["title"], "A")
        self.assertNotIn("extra", p1)          # champ non demandé exclu
        self.assertEqual(snap["feature"], "seo_boost")
        self.assertIn("created_at", snap)


class TestListAndLatest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.d   = os.path.join(self.tmp, BACKUPS_DIRNAME)
        os.makedirs(self.d)
        # Trois snapshots au nom horodaté (tri lexicographique = chronologique)
        self._write("seo_boost_2026-08-01_10-00-00.json", "seo_boost")
        self._write("seo_boost_2026-08-08_12-00-00.json", "seo_boost")
        self._write("fiche_produit_2026-08-05_09-00-00.json", "fiche_produit")

    def _write(self, name, feature):
        with open(os.path.join(self.d, name), "w", encoding="utf-8") as f:
            json.dump({"feature": feature, "created_at": name, "products": [{"id": 1}]}, f)

    def test_lists_most_recent_first(self):
        snaps = list_snapshots(self.tmp)
        self.assertEqual(snaps[0]["file"], "seo_boost_2026-08-08_12-00-00.json")

    def test_filter_by_feature(self):
        snaps = list_snapshots(self.tmp, feature="fiche_produit")
        self.assertEqual(len(snaps), 1)
        self.assertEqual(snaps[0]["feature"], "fiche_produit")

    def test_latest_snapshot_file(self):
        self.assertEqual(
            latest_snapshot_file(self.tmp, "seo_boost"),
            "seo_boost_2026-08-08_12-00-00.json",
        )

    def test_latest_none_when_empty(self):
        self.assertIsNone(latest_snapshot_file(tempfile.mkdtemp()))


class TestLoadSnapshot(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.file = os.path.basename(save_snapshot(self.tmp, "seo_boost", PRODUCTS, FIELDS))

    def test_loads_by_filename(self):
        snap = load_snapshot(self.tmp, self.file)
        self.assertEqual(len(snap["products"]), 2)

    def test_basename_only_prevents_traversal(self):
        # Un chemin avec ../ est réduit au basename → cherché dans backups/
        snap = load_snapshot(self.tmp, "../../etc/" + self.file)
        self.assertEqual(len(snap["products"]), 2)

    def test_invalid_name_raises(self):
        with self.assertRaises(ValueError):
            load_snapshot(self.tmp, "pas-un-json.txt")


if __name__ == "__main__":
    unittest.main()
