#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_seo_boost_title_attributes.py — Tests des cases à cocher qui contrôlent
les attributs du titre produit (dimensions, couleur, matériau…).
"""

import unittest
from unittest.mock import MagicMock

from features.seo_boost.prompts import (
    resolve_title_attributes,
    build_boost_differentiator_prompt,
    TITLE_ATTRIBUTES,
)
from features.seo_boost.generator import generate_differentiator


class TestResolveTitleAttributes(unittest.TestCase):

    def test_none_means_all_enabled(self):
        attrs = resolve_title_attributes(None)
        self.assertTrue(all(attrs.values()))
        self.assertEqual(set(attrs), {k for k, _ in TITLE_ATTRIBUTES})

    def test_missing_key_defaults_true(self):
        attrs = resolve_title_attributes({"color": False})
        self.assertFalse(attrs["color"])
        self.assertTrue(attrs["dimensions"])   # non fourni → True

    def test_explicit_false_respected(self):
        attrs = resolve_title_attributes({"dimensions": False, "color": False})
        self.assertFalse(attrs["dimensions"])
        self.assertFalse(attrs["color"])


class TestBuildDifferentiatorPrompt(unittest.TestCase):

    def test_excluded_attributes_listed_in_exclusion_block(self):
        prompt = build_boost_differentiator_prompt(
            "Boîte à bijoux", "Boîte à Bijoux", "", "",
            title_attributes={"color": False, "dimensions": False},
        )
        self.assertIn("NE PAS INCLURE", prompt)
        self.assertIn("Couleur", prompt)
        self.assertIn("Taille / dimensions", prompt)

    def test_no_exclusion_block_when_all_enabled(self):
        prompt = build_boost_differentiator_prompt("P", "N", "", "", title_attributes=None)
        self.assertNotIn("NE PAS INCLURE", prompt)

    def test_color_rule_only_when_color_enabled(self):
        with_color = build_boost_differentiator_prompt("P", "N", "", "", title_attributes={"color": True})
        without    = build_boost_differentiator_prompt("P", "N", "", "", title_attributes={"color": False})
        self.assertIn("couleur va en DERNIER", with_color)
        self.assertNotIn("couleur va en DERNIER", without)

    def test_dimensions_in_structure_when_enabled(self):
        prompt = build_boost_differentiator_prompt("P", "N", "", "", title_attributes={"dimensions": True})
        self.assertIn("Taille / dimensions", prompt)
        self.assertIn("ATTRIBUTS À INCLURE", prompt)

    def test_avoid_block_lists_taken_titles(self):
        p = build_boost_differentiator_prompt("P", "N", "", "", None, avoid=["XXL Bois Design"])
        self.assertIn("DÉJÀ PRISES", p)
        self.assertIn("XXL Bois Design", p)

    def test_no_avoid_block_without_avoid(self):
        p = build_boost_differentiator_prompt("P", "N", "", "", None)
        self.assertNotIn("DÉJÀ PRISES", p)


class TestGenerateDifferentiatorToggles(unittest.TestCase):

    def test_all_disabled_returns_empty_without_calling_openai(self):
        client  = MagicMock()
        tracker = MagicMock()
        all_off = {k: False for k, _ in TITLE_ATTRIBUTES}
        result  = generate_differentiator("P", "N", "", "", client, tracker, title_attributes=all_off)
        self.assertEqual(result, "")
        client.chat.completions.create.assert_not_called()

    def test_enabled_calls_openai(self):
        client = MagicMock()
        resp = MagicMock()
        resp.choices[0].message.content = "XXL Bois Design"
        resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5)
        client.chat.completions.create.return_value = resp
        tracker = MagicMock()
        tracker.cost_usd = 0.0
        result  = generate_differentiator("P", "N", "", "", client, tracker, title_attributes={"dimensions": False})
        self.assertEqual(result, "XXL Bois Design")
        client.chat.completions.create.assert_called_once()


if __name__ == "__main__":
    unittest.main()
