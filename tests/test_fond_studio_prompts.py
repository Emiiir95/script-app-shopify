"""
Tests unitaires — features/fond_studio/prompts.py
"""
import unittest

from features.fond_studio.prompts import build_background_prompt


class TestBuildBackgroundPrompt(unittest.TestCase):
    def test_includes_color(self):
        p = build_background_prompt("beige")
        self.assertIn("beige", p)

    def test_insists_on_identical_product(self):
        p = build_background_prompt("blanc").lower()
        self.assertIn("identical", p)
        self.assertIn("background", p)

    def test_asks_to_center_product(self):
        p = build_background_prompt("blanc").lower()
        self.assertIn("center", p)

    def test_empty_color_falls_back_to_white(self):
        p = build_background_prompt("")
        self.assertIn("white", p)

    def test_none_color_falls_back(self):
        p = build_background_prompt(None)
        self.assertIn("white", p)

    def test_strips_whitespace(self):
        p = build_background_prompt("  gris clair  ")
        self.assertIn("gris clair", p)
        self.assertNotIn("  gris clair  ", p)


if __name__ == "__main__":
    unittest.main()
