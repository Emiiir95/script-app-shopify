#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_taxonomy.py — Tests unitaires pour utils/taxonomy.py

Couvre : parsing, tokenisation/mots-clés, scoring lexical, collecte de candidats,
choix IA (mocké) et suggestion complète. Aucun appel réseau réel.
"""

import unittest
from unittest.mock import MagicMock

from utils.taxonomy import (
    parse_taxonomy_text,
    niche_match_keywords,
    rank_candidates,
    gather_candidates,
    choose_category_ai,
    suggest_categories,
)

SAMPLE = """# Shopify Product Taxonomy - Categories: test
gid://shopify/TaxonomyCategory/hb-2-3       : Santé et beauté > Entretien et nettoyage des bijoux > Présentoirs à bijoux
gid://shopify/TaxonomyCategory/hb-2-3-1     : Santé et beauté > Entretien et nettoyage des bijoux > Présentoirs à bijoux > Boîtes à bijoux
gid://shopify/TaxonomyCategory/hb-2-3-1-4   : Santé et beauté > Entretien et nettoyage des bijoux > Présentoirs à bijoux > Boîtes à bijoux > Boîtes à montres
gid://shopify/TaxonomyCategory/hb-2-3-2     : Santé et beauté > Entretien et nettoyage des bijoux > Présentoirs à bijoux > Support pour bijoux
gid://shopify/TaxonomyCategory/fr-4-1-7     : Meubles > Armoires et meubles de rangement > Armoires > Armoires à bijoux
gid://shopify/TaxonomyCategory/aa-6-11      : Vêtements et accessoires > Bijoux > Montres
ligne invalide sans separateur
"""


class TestParse(unittest.TestCase):

    def setUp(self):
        self.entries = parse_taxonomy_text(SAMPLE)

    def test_counts_valid_lines(self):
        self.assertEqual(len(self.entries), 6)   # 6 gids valides, commentaire + ligne invalide ignorés

    def test_gid_and_name(self):
        e = next(e for e in self.entries if e["gid"].endswith("hb-2-3-1-4"))
        self.assertEqual(e["name"], "Boîtes à montres")
        self.assertTrue(e["full_name"].endswith("Boîtes à montres"))

    def test_name_words_singularized(self):
        e = next(e for e in self.entries if e["gid"].endswith("hb-2-3-1-4"))
        self.assertIn("boite", e["name_words"])
        self.assertIn("montre", e["name_words"])

    def test_ignores_non_taxonomy_lines(self):
        for e in self.entries:
            self.assertTrue(e["gid"].startswith("gid://shopify/TaxonomyCategory/"))


class TestKeywords(unittest.TestCase):

    def test_multiword(self):
        self.assertEqual(niche_match_keywords("Boîte à Montre"), ["boite montre"])

    def test_accents_stopwords(self):
        self.assertEqual(niche_match_keywords("Armoire à Bijoux"), ["armoire bijoux"])

    def test_empty(self):
        self.assertEqual(niche_match_keywords("  à  "), [])


class TestRankAndGather(unittest.TestCase):

    def setUp(self):
        self.entries = parse_taxonomy_text(SAMPLE)

    def test_rank_best_is_exact(self):
        ranked = rank_candidates("Boîte à Bijoux", self.entries, top=5)
        self.assertEqual(ranked[0][1]["gid"].split("/")[-1], "hb-2-3-1")

    def test_rank_watch_box(self):
        ranked = rank_candidates("Boîte à Montre", self.entries, top=5)
        self.assertEqual(ranked[0][1]["gid"].split("/")[-1], "hb-2-3-1-4")

    def test_gather_includes_support_for_porte(self):
        # "Porte Bijoux" doit proposer "Support pour bijoux" (via dimension "bijoux")
        cands = gather_candidates("Porte Bijoux", self.entries)
        gids  = {e["gid"].split("/")[-1] for e in cands}
        self.assertIn("hb-2-3-2", gids)


class TestChooseAI(unittest.TestCase):

    def _client(self, content):
        client = MagicMock()
        msg = MagicMock()
        msg.choices = [MagicMock()]
        msg.choices[0].message.content = content
        client.chat.completions.create.return_value = msg
        return client

    def test_accepts_full_gid(self):
        cands = [{"gid": "gid://shopify/TaxonomyCategory/hb-2-3-2", "full_name": "x"}]
        client = self._client('{"gid": "gid://shopify/TaxonomyCategory/hb-2-3-2"}')
        self.assertEqual(choose_category_ai("Porte Bijoux", cands, client),
                         "gid://shopify/TaxonomyCategory/hb-2-3-2")

    def test_accepts_short_id(self):
        cands = [{"gid": "gid://shopify/TaxonomyCategory/hb-2-3-2", "full_name": "x"}]
        client = self._client('{"gid": "hb-2-3-2"}')   # le modèle renvoie l'id court
        self.assertEqual(choose_category_ai("Porte Bijoux", cands, client),
                         "gid://shopify/TaxonomyCategory/hb-2-3-2")

    def test_invalid_gid_returns_none(self):
        cands = [{"gid": "gid://shopify/TaxonomyCategory/hb-2-3-2", "full_name": "x"}]
        client = self._client('{"gid": "zz-9-9"}')
        self.assertIsNone(choose_category_ai("Porte Bijoux", cands, client))

    def test_exception_returns_none(self):
        cands = [{"gid": "gid://shopify/TaxonomyCategory/hb-2-3-2", "full_name": "x"}]
        client = MagicMock()
        client.chat.completions.create.side_effect = RuntimeError("boom")
        self.assertIsNone(choose_category_ai("Porte Bijoux", cands, client))


class TestSuggest(unittest.TestCase):

    def setUp(self):
        self.entries = parse_taxonomy_text(SAMPLE)

    def test_lexical_mode_no_client(self):
        rules = suggest_categories(["Boîte à Bijoux"], entries=self.entries)
        self.assertEqual(rules[0]["gid"].split("/")[-1], "hb-2-3-1")
        self.assertEqual(rules[0]["via"], "lexical")
        self.assertEqual(rules[0]["match"], ["boite bijoux"])
        self.assertTrue(rules[0]["found"])

    def test_ai_mode_picks_support(self):
        client = MagicMock()
        msg = MagicMock(); msg.choices = [MagicMock()]
        msg.choices[0].message.content = '{"gid": "hb-2-3-2"}'
        client.chat.completions.create.return_value = msg
        rules = suggest_categories(["Porte Bijoux"], entries=self.entries, _client=client)
        self.assertEqual(rules[0]["gid"].split("/")[-1], "hb-2-3-2")
        self.assertEqual(rules[0]["name"], "Support pour bijoux")
        self.assertEqual(rules[0]["via"], "ai")

    def test_skips_empty_niche(self):
        rules = suggest_categories(["", "  "], entries=self.entries)
        self.assertEqual(rules, [])

    def test_sorted_specific_first(self):
        rules = suggest_categories(["Bijoux", "Boîte à Montre Chic"], entries=self.entries)
        counts = [len(r["match"][0].split()) for r in rules]
        self.assertEqual(counts, sorted(counts, reverse=True))


if __name__ == "__main__":
    unittest.main()
