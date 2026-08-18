#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_balises_prompts.py — Feature Balises : construction du prompt de classement.
"""

import unittest

from features.balises.prompts import build_classification_prompt


COLS = [
    {"handle": "doudou", "title": "Doudou", "description": "Nos doudous"},
    {"handle": "rose",   "title": "Rose",   "description": ""},
]
CTX = {"title": "Doudou Lapin", "description": "tout doux", "product_type": "Doudou",
       "caracteristiques": "coton bio", "tags": "ancien"}


class TestBuildClassificationPrompt(unittest.TestCase):
    def test_contains_handles_and_product(self):
        p = build_classification_prompt(CTX, COLS)
        self.assertIn("doudou", p)
        self.assertIn("rose", p)
        self.assertIn("Doudou Lapin", p)
        self.assertIn("coton bio", p)
        self.assertIn('"collections"', p)   # format de sortie JSON imposé

    def test_no_cap_wording(self):
        p = build_classification_prompt(CTX, COLS, max_collections=0)
        self.assertIn("TOUTES les collections", p)

    def test_cap_wording(self):
        p = build_classification_prompt(CTX, COLS, max_collections=3)
        self.assertIn("AU PLUS 3", p)

    def test_handles_list_input_tags(self):
        ctx = dict(CTX, tags=["a", "b"])
        p = build_classification_prompt(ctx, COLS)
        self.assertIn("a, b", p)


if __name__ == "__main__":
    unittest.main()
