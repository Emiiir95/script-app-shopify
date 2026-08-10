#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_seo_boost_product_type.py — Détection du type de produit (boutique thématique).

Le type détecté remplace la niche fixe en début de titre (une boîte à montre ne doit
pas devenir « Boîte à Bijoux »).
"""

import unittest
from unittest.mock import MagicMock

from features.seo_boost.prompts import build_product_type_prompt
from features.seo_boost.generator import generate_product_type


class TestBuildProductTypePrompt(unittest.TestCase):
    def test_includes_title_and_description(self):
        p = build_product_type_prompt("Boîte à Montre Homme", "Un écrin pour montres.", "Boîte à Bijoux")
        self.assertIn("Boîte à Montre Homme", p)
        self.assertIn("écrin pour montres", p)
        self.assertIn("TYPE de produit", p)

    def test_niche_is_hint_not_obligation(self):
        p = build_product_type_prompt("X", "", "Boîte à Bijoux")
        self.assertIn("indice", p.lower())


class TestGenerateProductType(unittest.TestCase):
    def _client(self, content):
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = content
        resp.usage = MagicMock(prompt_tokens=50, completion_tokens=4)
        client.chat.completions.create.return_value = resp
        return client

    def _tracker(self):
        t = MagicMock(); t.cost_usd = 0.0; return t

    def test_returns_detected_type(self):
        client = self._client("Boîte à Montre")
        out = generate_product_type("Boîte à Montre Homme", "desc", "Boîte à Bijoux", client, self._tracker())
        self.assertEqual(out, "Boîte à Montre")

    def test_strips_quotes_and_caps_words(self):
        client = self._client('"Porte Bijoux Mural Design Élégant Extra Encore"')
        out = generate_product_type("Porte Bijoux", "d", "Boîte à Bijoux", client, self._tracker())
        self.assertLessEqual(len(out.split()), 5)      # max 5 mots (libre)
        self.assertFalse(out.startswith('"'))

    def test_prompt_lists_niches_when_provided(self):
        p = build_product_type_prompt("Boîte à Montre Homme", "d", "Boîte à Bijoux",
                                      niches=["Boîte à Bijoux", "Boîte à Montre"])
        self.assertIn("CATÉGORIES DE LA BOUTIQUE", p)
        self.assertIn("Boîte à Montre", p)

    def test_snaps_to_exact_niche_from_list(self):
        # L'IA renvoie une variation (pluriel/casse/accent) → on verrouille l'orthographe de la liste
        client = self._client("boites a montres")
        out = generate_product_type("Boîte à Montre Homme", "d", "Boîte à Bijoux", client, self._tracker(),
                                    niches=["Boîte à Bijoux", "Boîte à Montre"])
        self.assertEqual(out, "Boîte à Montre")

    def test_keeps_ai_proposal_if_no_niche_matches(self):
        client = self._client("Coffret Parfum")
        out = generate_product_type("X", "d", "", client, self._tracker(),
                                    niches=["Boîte à Bijoux", "Boîte à Montre"])
        self.assertEqual(out, "Coffret Parfum")        # aucune correspondance → garde la proposition

    def test_fallback_to_niche_on_failure(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API down")
        out = generate_product_type("Titre", "d", "Boîte à Bijoux", client, self._tracker(), max_retries=1)
        self.assertEqual(out, "Boîte à Bijoux")        # repli sur la niche

    def test_fallback_to_title_when_no_niche(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("x")
        out = generate_product_type("Mon Produit", "d", "", client, self._tracker(), max_retries=1)
        self.assertEqual(out, "Mon Produit")


if __name__ == "__main__":
    unittest.main()
