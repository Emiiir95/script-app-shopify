"""
Tests unitaires — features/seo_boost/generator.py (construction du H1)

Couvre build_h1 pour les 3 modes de titre :
  - characteristics : niche + SEO complet, sans marque
  - branded         : marque + niche + SEO court (2 mots-clés max)
  - seo_branded     : marque + niche + SEO complet
"""
import unittest

from features.seo_boost.generator import build_h1, _first_words


NICHE = "Griffoir Chat"
DIFF  = "XXL Sisal Beige"   # 3 mots-clés SEO après nettoyage
BRAND = "LumiNest"


class TestFirstWords(unittest.TestCase):
    def test_keeps_first_n(self):
        self.assertEqual(_first_words("a b c d", 2), "a b")

    def test_returns_all_when_fewer(self):
        self.assertEqual(_first_words("a", 2), "a")

    def test_empty(self):
        self.assertEqual(_first_words("", 2), "")


class TestBuildH1Characteristics(unittest.TestCase):
    def test_no_brand_full_seo(self):
        h1 = build_h1("", NICHE, DIFF, title_style="characteristics")
        self.assertEqual(h1, "Griffoir Chat XXL Sisal Beige")

    def test_default_style_is_characteristics(self):
        # title_style non fourni → comportement characteristics (rétrocompat)
        self.assertEqual(build_h1("", NICHE, DIFF), "Griffoir Chat XXL Sisal Beige")

    def test_empty_differentiator_gives_niche_only(self):
        self.assertEqual(build_h1("", NICHE, "", title_style="characteristics"), "Griffoir Chat")


class TestBuildH1Branded(unittest.TestCase):
    def test_brand_start_short_seo(self):
        # branded = marque en avant + SEO tronqué à 2 mots
        h1 = build_h1(BRAND, NICHE, DIFF, branding_position="start", title_style="branded")
        self.assertEqual(h1, "LumiNest – Griffoir Chat XXL Sisal")

    def test_brand_end_short_seo(self):
        h1 = build_h1(BRAND, NICHE, DIFF, branding_position="end", title_style="branded")
        self.assertEqual(h1, "Griffoir Chat XXL Sisal – LumiNest")

    def test_seo_is_truncated_to_two_words(self):
        h1 = build_h1(BRAND, NICHE, "A B C D E", branding_position="start", title_style="branded")
        self.assertEqual(h1, "LumiNest – Griffoir Chat A B")

    def test_brand_present(self):
        h1 = build_h1(BRAND, NICHE, DIFF, title_style="branded")
        self.assertIn(BRAND, h1)


class TestBuildH1SeoBranded(unittest.TestCase):
    def test_brand_start_full_seo(self):
        # seo_branded = marque + SEO complet (pas de troncature)
        h1 = build_h1(BRAND, NICHE, DIFF, branding_position="start", title_style="seo_branded")
        self.assertEqual(h1, "LumiNest – Griffoir Chat XXL Sisal Beige")

    def test_brand_end_full_seo(self):
        h1 = build_h1(BRAND, NICHE, DIFF, branding_position="end", title_style="seo_branded")
        self.assertEqual(h1, "Griffoir Chat XXL Sisal Beige – LumiNest")

    def test_keeps_all_seo_words(self):
        h1 = build_h1(BRAND, NICHE, "A B C D E", branding_position="start", title_style="seo_branded")
        self.assertEqual(h1, "LumiNest – Griffoir Chat A B C D E")


class TestBuildH1ModesDiffer(unittest.TestCase):
    def test_branded_shorter_than_seo_branded(self):
        branded     = build_h1(BRAND, NICHE, DIFF, title_style="branded")
        seo_branded = build_h1(BRAND, NICHE, DIFF, title_style="seo_branded")
        self.assertNotEqual(branded, seo_branded)
        self.assertLess(len(branded), len(seo_branded))

    def test_characteristics_has_no_brand(self):
        h1 = build_h1("", NICHE, DIFF, title_style="characteristics")
        self.assertNotIn(BRAND, h1)


if __name__ == "__main__":
    unittest.main()
