#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_seo_boost_unique_title.py — Déduplication des titres (make_unique_title).

Empêche les titres/handles dupliqués (→ plus d'URL en -1/-2 ajoutées par Shopify).
"""

import unittest

from features.seo_boost.runner import make_unique_title


class TestMakeUniqueTitle(unittest.TestCase):
    def test_no_collision_returns_unchanged(self):
        self.assertEqual(make_unique_title("Boîte Bois", "Boîte 10cm Bois", set()), "Boîte Bois")

    def test_collision_appends_dimension(self):
        used = {"Boîte à Bijoux Bois Élégant"}
        out  = make_unique_title("Boîte à Bijoux Bois Élégant", "Boîte à Bijoux 18,5cm Bois Verni", used)
        self.assertIn("18,5cm", out.replace(" ", ""))   # dimension greffée
        self.assertNotIn(out, used)

    def test_collision_appends_distinctive_word_when_no_dimension(self):
        used = {"Boîte à Bijoux Cuir"}
        out  = make_unique_title("Boîte à Bijoux Cuir", "Boîte à Bijoux Velours Rose", used)
        # un mot distinctif du titre d'origine (velours ou rose), absent du H1
        self.assertTrue(out.lower().endswith("velours") or out.lower().endswith("rose"))
        self.assertNotIn(out, used)

    def test_numeric_fallback_when_identical(self):
        used = {"Produit"}
        out  = make_unique_title("Produit", "Produit", used)   # aucun détail distinctif
        self.assertEqual(out, "Produit 2")

    def test_only_enabled_categories_used_when_they_suffice(self):
        # couleur décochée ; matériau coché et suffit à distinguer → pas de couleur ajoutée
        attrs = {"color": False, "dimensions": False, "material": True,
                 "feature": True, "style": True, "commercial_keyword": True}
        used  = {"Boîte à Bijoux Cuir Élégant"}
        out   = make_unique_title("Boîte à Bijoux Cuir Élégant",
                                  "Boîte à Bijoux Velours Rose", used, attrs)
        self.assertIn("Velours", out)          # matériau (coché) utilisé
        self.assertNotIn("Rose", out)          # couleur (décochée) PAS ajoutée

    def test_tiebreaker_uses_disabled_category_as_last_resort(self):
        # couleur décochée MAIS 2 produits ne diffèrent QUE par la couleur → couleur en dernier recours
        attrs = {"color": False, "dimensions": False, "material": True,
                 "feature": True, "style": True, "commercial_keyword": True}
        used  = {"Boîte à Bijoux Cuir Élégant"}
        out   = make_unique_title("Boîte à Bijoux Cuir Élégant",
                                  "Boîte à Bijoux Cuir Rose", used, attrs)
        self.assertTrue(out.lower().endswith("rose"))   # couleur ajoutée SEULEMENT car nécessaire
        self.assertNotIn(out, used)

    def test_chain_of_collisions_stays_unique(self):
        used = set()
        titles = []
        for _ in range(5):
            t = make_unique_title("Boîte à Bijoux Bois Élégant",
                                   "Boîte à Bijoux 20cm Bois Massif Verni Naturel", used)
            used.add(t); titles.append(t)
        self.assertEqual(len(set(titles)), 5)   # 5 titres tous distincts


if __name__ == "__main__":
    unittest.main()
