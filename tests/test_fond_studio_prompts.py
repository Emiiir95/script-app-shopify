"""
Tests unitaires — features/fond_studio/prompts.py
"""
import unittest

from features.fond_studio.prompts import (
    build_background_prompt, build_scene_prompt, SCENE_TEMPLATES, _hex_to_rgb,
)


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

    def test_hex_includes_hex_and_rgb(self):
        p = build_background_prompt("#F7F7F7")
        self.assertIn("#F7F7F7", p)            # hex exact répété
        self.assertIn("247,247,247", p)         # composantes RGB

    def test_hex_short_form_expanded(self):
        p = build_background_prompt("#fff")
        self.assertIn("#FFFFFF", p)
        self.assertIn("255,255,255", p)

    def test_forbids_gradient_and_drift(self):
        p = build_background_prompt("#F7F7F7").lower()
        self.assertIn("gradient", p)            # interdiction explicite
        self.assertIn("drift", p)

    def test_hex_still_keeps_product_rules(self):
        p = build_background_prompt("#123456").lower()
        self.assertIn("identical", p)
        self.assertIn("center", p)


class TestHexToRgb(unittest.TestCase):
    def test_full_hex(self):
        self.assertEqual(_hex_to_rgb("#F7F7F7"), (247, 247, 247))

    def test_without_hash(self):
        self.assertEqual(_hex_to_rgb("000000"), (0, 0, 0))

    def test_short_form(self):
        self.assertEqual(_hex_to_rgb("#abc"), (170, 187, 204))

    def test_non_hex_returns_none(self):
        self.assertIsNone(_hex_to_rgb("beige"))
        self.assertIsNone(_hex_to_rgb(""))
        self.assertIsNone(_hex_to_rgb(None))


class TestBuildScenePrompt(unittest.TestCase):
    def test_known_scene_includes_its_description(self):
        p = build_scene_prompt("luxe").lower()
        self.assertIn("luxury", p)          # description de la scène "luxe"
        self.assertIn("identical", p)       # règles produit conservées
        self.assertIn("center", p)

    def test_unknown_scene_falls_back_to_minimalist(self):
        p = build_scene_prompt("nawak").lower()
        self.assertIn("minimalist", p)      # fallback
        self.assertIn("identical", p)

    def test_templates_have_label_and_scene(self):
        self.assertIn("luxe", SCENE_TEMPLATES)
        self.assertIn("mode", SCENE_TEMPLATES)
        for key, tpl in SCENE_TEMPLATES.items():
            self.assertIn("label", tpl)
            self.assertIn("scene", tpl)


if __name__ == "__main__":
    unittest.main()
