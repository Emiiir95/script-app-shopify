#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_seo_boost_maillage.py — Tests de la sélection des collections pour le
maillage interne (features/seo_boost/runner.select_collections_for_product).

Vérifie notamment le bug « un seul lien (collection principale) » : sans tags,
le matching doit se faire sur les MOTS DISTINCTIFS du nom de collection.
"""

import unittest

from features.seo_boost.runner import (
    select_collections_for_product,
    _is_variation_collection,
    _normalize_col_text,
    _parse_tag_set,
)


BOOST_CFG = {
    "niche_keyword": "Boîte à Bijoux",
    "mainCollection": {"name": "Toutes Nos Boîtes À Bijoux", "url": "https://x.com/collections/boites-a-bijoux", "volume": 22200},
    "collections": [
        {"name": "Boite À Bijoux Bois",   "url": "https://x.com/collections/boite-a-bijoux-bois",   "volume": 1000},
        {"name": "Boite À Bijoux Cuir",   "url": "https://x.com/collections/boite-a-bijoux-cuir",   "volume": 390},
        {"name": "Grande Boite À Bijoux", "url": "https://x.com/collections/grande-boite-a-bijoux", "volume": 260},
        {"name": "Petite Boite À Bijoux", "url": "https://x.com/collections/petite-boite-a-bijoux", "volume": 480},
        {"name": "Boite À Bijoux Femme",  "url": "https://x.com/collections/boite-a-bijoux-femme",  "volume": 590},
    ],
}


class TestSelectCollectionsForProduct(unittest.TestCase):

    def _urls(self, selected):
        return [c["url"] for c in selected]

    def test_main_collection_always_present(self):
        sel = select_collections_for_product("Produit sans rapport", "", BOOST_CFG)
        self.assertEqual(sel[0]["url"], BOOST_CFG["mainCollection"]["url"])

    def test_only_main_when_no_distinctive_match(self):
        # Texte produit purement générique (que des mots de la niche) → aucun mot distinctif
        sel = select_collections_for_product("Boîte à bijoux magnifique", "boite a bijoux elegante", BOOST_CFG)
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0]["url"], BOOST_CFG["mainCollection"]["url"])

    def test_matches_type_collection_by_distinctive_word(self):
        # "bois" est distinctif → doit lier la collection "Boite À Bijoux Bois"
        sel = select_collections_for_product("Boîte à bijoux en bois massif", "coffret bois", BOOST_CFG)
        urls = self._urls(sel)
        self.assertIn("https://x.com/collections/boite-a-bijoux-bois", urls)
        self.assertGreaterEqual(len(sel), 2)   # plus que la seule principale

    def test_matches_type_and_variation(self):
        # "bois" (type) + "grande" (variation) → 3 liens : principale + type + variation
        sel = select_collections_for_product("Grande boîte à bijoux en bois", "", BOOST_CFG)
        urls = self._urls(sel)
        self.assertIn(BOOST_CFG["mainCollection"]["url"], urls)
        self.assertIn("https://x.com/collections/boite-a-bijoux-bois", urls)
        self.assertIn("https://x.com/collections/grande-boite-a-bijoux", urls)
        self.assertEqual(len(sel), 3)

    def test_never_more_than_three_links(self):
        sel = select_collections_for_product("Grande boîte à bijoux en bois et cuir pour femme", "", BOOST_CFG)
        self.assertLessEqual(len(sel), 3)

    def test_generic_niche_words_do_not_match(self):
        # "boite"/"bijoux" sont génériques : ne doivent pas suffire à matcher une collection
        sel = select_collections_for_product("Une boîte à bijoux", "", BOOST_CFG)
        self.assertEqual(len(sel), 1)

    def test_explicit_tags_still_work(self):
        cfg = {
            "niche_keyword": "Boîte à Bijoux",
            "mainCollection": {"name": "Principale", "url": "https://x.com/collections/main", "volume": 100},
            "collections": [
                {"name": "Collection Spéciale", "url": "https://x.com/collections/spe", "volume": 10,
                 "tags": ["velours rose"]},
            ],
        }
        sel = select_collections_for_product("Boîte en velours rose", "", cfg)
        self.assertIn("https://x.com/collections/spe", self._urls(sel))

    def test_no_collections_returns_main_only(self):
        cfg = {"niche_keyword": "X", "mainCollection": {"name": "M", "url": "https://x/m", "volume": 1}, "collections": []}
        sel = select_collections_for_product("Titre", "desc", cfg)
        self.assertEqual(len(sel), 1)

    def test_no_main_collection(self):
        cfg = {"niche_keyword": "Boîte à Bijoux", "collections": BOOST_CFG["collections"]}
        sel = select_collections_for_product("Boîte à bijoux en bois", "", cfg)
        # pas de principale, mais le type "bois" doit quand même matcher
        self.assertIn("https://x.com/collections/boite-a-bijoux-bois", self._urls(sel))


class TestSelectByProductTags(unittest.TestCase):
    """Matching prioritaire par tags Shopify du produit (le plus fiable)."""

    def _urls(self, selected):
        return [c["url"] for c in selected]

    def test_tag_matches_collection_by_name(self):
        # Tag produit = nom exact d'une collection → lien direct, sans texte
        sel = select_collections_for_product(
            "Titre neutre", "description neutre", BOOST_CFG,
            product_tags="Boite À Bijoux Bois, Grande Boite À Bijoux",
        )
        urls = self._urls(sel)
        self.assertIn("https://x.com/collections/boite-a-bijoux-bois", urls)
        self.assertIn("https://x.com/collections/grande-boite-a-bijoux", urls)
        self.assertEqual(len(sel), 3)   # principale + type + variation

    def test_tags_accept_list_input(self):
        sel = select_collections_for_product(
            "T", "", BOOST_CFG, product_tags=["Boite À Bijoux Cuir"],
        )
        self.assertIn("https://x.com/collections/boite-a-bijoux-cuir", self._urls(sel))

    def test_tags_prioritized_over_text(self):
        # Le texte contient "bois" mais le tag est "cuir" → cuir (tag) doit primer.
        # bois peut apparaître en complément, mais APRÈS cuir (priorité aux tags).
        sel = select_collections_for_product(
            "Boîte à bijoux en bois", "vraiment du bois", BOOST_CFG,
            product_tags="Boite À Bijoux Cuir",
        )
        urls = self._urls(sel)
        self.assertIn("https://x.com/collections/boite-a-bijoux-cuir", urls)
        if "https://x.com/collections/boite-a-bijoux-bois" in urls:
            self.assertLess(
                urls.index("https://x.com/collections/boite-a-bijoux-cuir"),
                urls.index("https://x.com/collections/boite-a-bijoux-bois"),
            )

    def test_tag_not_matching_any_collection_gives_main_only(self):
        sel = select_collections_for_product(
            "T", "", BOOST_CFG, product_tags="tag-inconnu, autre-tag",
        )
        self.assertEqual(len(sel), 1)
        self.assertEqual(sel[0]["url"], BOOST_CFG["mainCollection"]["url"])

    def test_empty_tags_falls_back_to_text(self):
        # Pas de tags → fallback texte : "bois" doit matcher
        sel = select_collections_for_product(
            "Boîte à bijoux en bois", "", BOOST_CFG, product_tags="",
        )
        self.assertIn("https://x.com/collections/boite-a-bijoux-bois", self._urls(sel))


class TestParseTagSet(unittest.TestCase):

    def test_csv_string(self):
        self.assertEqual(_parse_tag_set("Bois, Cuir , Femme"), {"bois", "cuir", "femme"})

    def test_list_input(self):
        self.assertEqual(_parse_tag_set(["Bois", "Cuir"]), {"bois", "cuir"})

    def test_empty(self):
        self.assertEqual(_parse_tag_set(""), set())
        self.assertEqual(_parse_tag_set(None), set())


class TestIsVariationCollection(unittest.TestCase):

    def test_size_word_is_variation(self):
        self.assertTrue(_is_variation_collection("Grande Boîte À Bijoux"))
        self.assertTrue(_is_variation_collection("Petite Boîte À Bijoux"))

    def test_color_word_is_variation(self):
        self.assertTrue(_is_variation_collection("Boîte Beige"))

    def test_type_word_is_not_variation(self):
        self.assertFalse(_is_variation_collection("Boîte À Bijoux Bois"))


class TestNormalizeColText(unittest.TestCase):

    def test_accents_and_case(self):
        self.assertEqual(_normalize_col_text("Boîte À Bijoux"), "boite a bijoux")

    def test_hyphens_to_space(self):
        self.assertEqual(_normalize_col_text("boite-a-bijoux"), "boite a bijoux")


if __name__ == "__main__":
    unittest.main()
