#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests — H1/meta title naturels générés par l'IA (best practices)."""

import unittest
from unittest.mock import MagicMock

from features.seo_boost.prompts import build_natural_title_prompt
from features.seo_boost.generator import generate_natural_title


class TestBuildNaturalTitlePrompt(unittest.TestCase):
    def test_contains_product_niche_and_json(self):
        p = build_natural_title_prompt("Support Collier Métal", "desc", "Porte Bijoux")
        self.assertIn("Support Collier Métal", p)
        self.assertIn("Porte Bijoux", p)
        self.assertIn('"h1"', p)
        self.assertIn('"meta_title"', p)

    def test_lists_excluded_attributes(self):
        p = build_natural_title_prompt("P", "", "N", title_attributes={"color": False, "dimensions": False})
        self.assertIn("NE PAS inclure", p)
        self.assertIn("Couleur", p)

    def test_branding_instruction_when_branded(self):
        p = build_natural_title_prompt("P", "", "N", branding_name="Lumia",
                                       branding_position="start", title_style="branded")
        self.assertIn("Lumia", p)
        self.assertIn("MARQUE", p)

    def test_avoid_block(self):
        p = build_natural_title_prompt("P", "", "N", avoid=["Titre Pris"])
        self.assertIn("DÉJÀ PRIS", p)
        self.assertIn("Titre Pris", p)

    def test_seo_keywords_block_targets_search_terms(self):
        p = build_natural_title_prompt("P", "", "N",
                                       seo_keywords="boite a bijoux femme (volume 5400)")
        self.assertIn("RECHERCHÉS SUR GOOGLE", p)
        self.assertIn("boite a bijoux femme", p)

    def test_no_seo_block_without_keywords(self):
        p = build_natural_title_prompt("P", "", "N")
        self.assertNotIn("RECHERCHÉS SUR GOOGLE", p)

    def test_forbids_technical_abbreviations(self):
        p = build_natural_title_prompt("Boîte Cuir PU", "", "Boîte à Bijoux")
        self.assertIn("codes techniques", p)            # pas de jargon type PU/MDF
        self.assertIn("PU", p)

    def test_bans_decorative_adjectives(self):
        p = build_natural_title_prompt("P", "", "N")
        self.assertIn("BANNIS", p)
        self.assertIn("élégant", p)                     # adjectif vide cité comme interdit

    def test_meta_title_distinct_from_h1(self):
        p = build_natural_title_prompt("P", "", "N")
        self.assertIn("RÈGLES META TITLE", p)
        self.assertIn("DIFFÉREMMENT", p)                # meta title != H1 mot pour mot
        self.assertIn("50 à 60", p)                     # longueur idéale


class TestGenerateNaturalTitle(unittest.TestCase):
    def _client(self, content):
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = content
        resp.usage = MagicMock(prompt_tokens=100, completion_tokens=20)
        client.chat.completions.create.return_value = resp
        return client

    def _tracker(self):
        t = MagicMock(); t.cost_usd = 0.0; return t

    def test_returns_h1_and_meta(self):
        client = self._client('{"h1":"Support à Colliers Métal","meta_title":"Support à Colliers Métal Design"}')
        h1, mt = generate_natural_title("Support Collier", "d", "Porte Bijoux", None,
                                        "", "start", "characteristics", client, self._tracker())
        self.assertEqual(h1, "Support à Colliers Métal")
        self.assertEqual(mt, "Support à Colliers Métal Design")

    def test_meta_falls_back_to_h1_if_missing(self):
        client = self._client('{"h1":"Boîte à Montre Cuir"}')
        h1, mt = generate_natural_title("X", "d", "Boîte à Montre", None,
                                        "", "start", "characteristics", client, self._tracker())
        self.assertEqual(mt, "Boîte à Montre Cuir")     # meta = h1 si absent

    def test_includes_image_when_url_provided(self):
        client = self._client('{"h1":"H","meta_title":"M"}')
        generate_natural_title("P", "d", "N", None, "", "start", "characteristics",
                               client, self._tracker(), image_url="https://cdn/x.jpg")
        content = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIsInstance(content, list)                          # message multimodal
        self.assertTrue(any(p.get("type") == "image_url" for p in content))

    def test_text_only_when_no_image(self):
        client = self._client('{"h1":"H","meta_title":"M"}')
        generate_natural_title("P", "d", "N", None, "", "start", "characteristics",
                               client, self._tracker())
        content = client.chat.completions.create.call_args.kwargs["messages"][0]["content"]
        self.assertIsInstance(content, str)                           # texte seul

    def test_fallback_to_supplier_title_on_failure(self):
        client = MagicMock()
        client.chat.completions.create.side_effect = Exception("API down")
        h1, mt = generate_natural_title("Boîte à Bijoux 10cm Cuir", "d", "Boîte à Bijoux", None,
                                        "", "start", "characteristics", client, self._tracker(), max_retries=1)
        self.assertEqual(h1, "Boîte à Bijoux 10cm Cuir")   # repli sur le titre fournisseur
        self.assertEqual(mt, "Boîte à Bijoux 10cm Cuir")


if __name__ == "__main__":
    unittest.main()
