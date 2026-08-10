#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_normalisation.py — Tests unitaires pour features/normalisation/

Couvre :
  - compute_variant_changes  : logique prix + détection changements
  - normalize_product        : PUT produit + PUT variantes
  - generate_injection_report: création CSV post-injection
"""

import csv
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch, call

from features.normalisation.injector import (
    compute_variant_changes,
    normalize_product,
    resolve_steps,
    match_category_rule,
    resolve_rule_gids,
    niche_to_match_keywords,
    suggest_categories_for_niches,
    generate_injection_report,
)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _variant(price, compare_at=None, taxable=False, inv_policy="deny",
             fulfillment="manual", requires_shipping=True, sku="SKU1", vid=101):
    return {
        "id":                   vid,
        "sku":                  sku,
        "price":                str(price),
        "compare_at_price":     str(compare_at) if compare_at is not None else None,
        "taxable":              taxable,
        "inventory_policy":     inv_policy,
        "fulfillment_service":  fulfillment,
        "requires_shipping":    requires_shipping,
    }


def _product(pid=1, handle="test-handle", title="Test", status="active", variants=None):
    return {
        "id":       pid,
        "handle":   handle,
        "title":    title,
        "status":   status,
        "variants": variants or [_variant(29.99)],
    }


BASE_URL = "https://test.myshopify.com/admin/api/2026-01"
HEADERS  = {"X-Shopify-Access-Token": "test"}


# ── compute_variant_changes ───────────────────────────────────────────────────

class TestComputeVariantChanges(unittest.TestCase):

    def test_compare_at_higher_sets_new_price(self):
        v = _variant(price=29.99, compare_at=49.99)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "49.99")

    def test_compare_at_lower_keeps_price(self):
        v = _variant(price=59.99, compare_at=39.99)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "59.99")

    def test_no_compare_at_keeps_price(self):
        v = _variant(price=39.99, compare_at=None)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "39.99")

    def test_equal_prices_keeps_price(self):
        v = _variant(price=30.00, compare_at=30.00)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "30.00")

    def test_changed_false_when_already_normalized(self):
        v = _variant(price=39.99, compare_at=None, taxable=False,
                     inv_policy="deny", fulfillment="manual", requires_shipping=True)
        c = compute_variant_changes(v)
        self.assertFalse(c["changed"])

    def test_changed_true_when_compare_at_nonzero(self):
        # compare_at non vide → doit être vidé → changed=True
        v = _variant(price=39.99, compare_at=39.99)
        c = compute_variant_changes(v)
        self.assertTrue(c["changed"])

    def test_changed_true_when_taxable_true(self):
        v = _variant(price=39.99, compare_at=None, taxable=True)
        c = compute_variant_changes(v)
        self.assertTrue(c["changed"])

    def test_changed_true_when_inventory_policy_wrong(self):
        v = _variant(price=39.99, compare_at=None, inv_policy="continue")
        c = compute_variant_changes(v)
        self.assertTrue(c["changed"])

    def test_changed_true_when_fulfillment_wrong(self):
        v = _variant(price=39.99, compare_at=None, fulfillment="gift_card")
        c = compute_variant_changes(v)
        self.assertTrue(c["changed"])

    def test_prix_avant_preserved(self):
        v = _variant(price=29.99, compare_at=49.99)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_avant"], "29.99")
        self.assertEqual(c["compare_at_avant"], "49.99")

    def test_invalid_price_does_not_raise(self):
        v = _variant(price="", compare_at=None)
        c = compute_variant_changes(v)
        self.assertEqual(c["prix_apres"], "0.00")


class TestComputeVariantChangesPriceMode(unittest.TestCase):
    """price_mode : keep_price | use_compare | max (défaut)."""

    def test_keep_price_uses_price(self):
        v = _variant(price=20.00, compare_at=50.00)
        c = compute_variant_changes(v, price_mode="keep_price")
        self.assertEqual(c["prix_apres"], "20.00")

    def test_keep_price_ignores_compare(self):
        v = _variant(price=59.99, compare_at=39.99)
        c = compute_variant_changes(v, price_mode="keep_price")
        self.assertEqual(c["prix_apres"], "59.99")

    def test_use_compare_uses_compare(self):
        v = _variant(price=20.00, compare_at=50.00)
        c = compute_variant_changes(v, price_mode="use_compare")
        self.assertEqual(c["prix_apres"], "50.00")

    def test_use_compare_without_compare_keeps_price(self):
        # sécurité : pas de prix barré → on garde le prix, jamais 0
        v = _variant(price=39.99, compare_at=None)
        c = compute_variant_changes(v, price_mode="use_compare")
        self.assertEqual(c["prix_apres"], "39.99")

    def test_max_is_default(self):
        v = _variant(price=20.00, compare_at=50.00)
        self.assertEqual(compute_variant_changes(v)["prix_apres"],
                         compute_variant_changes(v, price_mode="max")["prix_apres"])
        self.assertEqual(compute_variant_changes(v)["prix_apres"], "50.00")


# ── normalize_product ─────────────────────────────────────────────────────────

class TestNormalizeProduct(unittest.TestCase):

    @patch("features.normalisation.injector.shopify_put")
    def test_puts_each_variant(self, mock_put):
        mock_put.return_value = {}
        variants = [_variant(29.99, vid=101, sku="A"), _variant(39.99, vid=102, sku="B")]
        product  = _product(pid=1, status="active", variants=variants)

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique")

        # 1 PUT produit + 2 PUT variantes = 3 calls total
        self.assertEqual(mock_put.call_count, 3)
        urls = [c.args[0] for c in mock_put.call_args_list]
        self.assertIn(f"{BASE_URL}/variants/101.json", urls)
        self.assertIn(f"{BASE_URL}/variants/102.json", urls)

    @patch("features.normalisation.injector.shopify_put")
    def test_puts_product_always(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=5, status="draft", variants=[_variant(10.00, vid=200)])

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique")

        # 1 PUT produit + 1 PUT variante = 2 calls total
        self.assertEqual(mock_put.call_count, 2)
        product_url = f"{BASE_URL}/products/5.json"
        urls = [c.args[0] for c in mock_put.call_args_list]
        self.assertIn(product_url, urls)

    @patch("features.normalisation.injector.shopify_put")
    def test_product_payload_includes_vendor(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=5, status="active", variants=[_variant(10.00, vid=200)])

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique")

        product_call = next(c for c in mock_put.call_args_list if "products" in c.args[0])
        payload = product_call.args[2]["product"]
        self.assertEqual(payload["vendor"], "Ma Boutique")
        self.assertEqual(payload["status"], "active")

    @patch("features.normalisation.injector.shopify_put")
    def test_variant_payload_has_correct_fields(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=1, status="active", variants=[_variant(29.99, compare_at=49.99, vid=101)])

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique")

        variant_call = next(
            c for c in mock_put.call_args_list
            if "variants" in c.args[0]
        )
        payload = variant_call.args[2]["variant"]
        self.assertEqual(payload["price"], "49.99")
        self.assertIsNone(payload["compare_at_price"])
        self.assertFalse(payload["taxable"])
        self.assertEqual(payload["inventory_policy"], "deny")
        self.assertEqual(payload["fulfillment_service"], "manual")
        self.assertTrue(payload["requires_shipping"])

    @patch("features.normalisation.injector.shopify_put")
    def test_returns_one_entry_per_variant(self, mock_put):
        mock_put.return_value = {}
        variants = [_variant(10.00, vid=1), _variant(20.00, vid=2), _variant(30.00, vid=3)]
        product  = _product(status="active", variants=variants)

        results = normalize_product(product, BASE_URL, HEADERS, "Ma Boutique")
        self.assertEqual(len(results), 3)


# ── resolve_steps ─────────────────────────────────────────────────────────────

class TestResolveSteps(unittest.TestCase):

    KEYS = {"prix", "stock_taxes", "fournisseur", "categorie", "couleurs"}

    def test_none_all_enabled(self):
        r = resolve_steps(None)
        self.assertEqual(set(r), self.KEYS)
        self.assertTrue(all(r.values()))

    def test_empty_all_enabled(self):
        self.assertTrue(all(resolve_steps({}).values()))

    def test_missing_key_defaults_true(self):
        r = resolve_steps({"prix": False})
        self.assertFalse(r["prix"])
        self.assertTrue(r["couleurs"])   # clé absente → activée

    def test_false_disables(self):
        r = resolve_steps({"prix": False, "couleurs": False})
        self.assertFalse(r["prix"])
        self.assertFalse(r["couleurs"])
        self.assertTrue(r["fournisseur"])

    def test_none_value_treated_as_enabled(self):
        self.assertTrue(resolve_steps({"prix": None})["prix"])


# ── normalize_product — respect des steps ──────────────────────────────────────

class TestNormalizeProductSteps(unittest.TestCase):

    @patch("features.normalisation.injector.shopify_put")
    def test_fournisseur_off_skips_product_put(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=5, status="active", variants=[_variant(10.00, vid=200)])

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique",
                          steps={"fournisseur": False})

        urls = [c.args[0] for c in mock_put.call_args_list]
        self.assertNotIn(f"{BASE_URL}/products/5.json", urls)
        self.assertIn(f"{BASE_URL}/variants/200.json", urls)

    @patch("features.normalisation.injector.shopify_put")
    def test_prix_off_omits_price_fields(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=1, status="active",
                           variants=[_variant(29.99, compare_at=49.99, vid=101)])

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique",
                          steps={"prix": False})

        variant_call = next(c for c in mock_put.call_args_list if "variants" in c.args[0])
        payload = variant_call.args[2]["variant"]
        self.assertNotIn("price", payload)
        self.assertNotIn("compare_at_price", payload)
        self.assertFalse(payload["taxable"])   # stock_taxes reste activé

    @patch("features.normalisation.injector.shopify_put")
    def test_stock_taxes_off_omits_variant_fields(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=1, status="active",
                           variants=[_variant(29.99, compare_at=49.99, vid=101)])

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique",
                          steps={"stock_taxes": False})

        variant_call = next(c for c in mock_put.call_args_list if "variants" in c.args[0])
        payload = variant_call.args[2]["variant"]
        self.assertEqual(payload["price"], "49.99")
        self.assertNotIn("taxable", payload)
        self.assertNotIn("inventory_policy", payload)

    @patch("features.normalisation.injector.shopify_put")
    def test_both_variant_parts_off_skips_variant_put(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=1, status="active", variants=[_variant(29.99, vid=101)])

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique",
                          steps={"prix": False, "stock_taxes": False})

        urls = [c.args[0] for c in mock_put.call_args_list]
        self.assertNotIn(f"{BASE_URL}/variants/101.json", urls)
        # le produit (vendor) reste écrit
        self.assertIn(f"{BASE_URL}/products/1.json", urls)

    @patch("features.normalisation.injector.shopify_put")
    def test_prix_off_report_keeps_original_price(self, mock_put):
        mock_put.return_value = {}
        product = _product(pid=1, status="active",
                           variants=[_variant(29.99, compare_at=49.99, vid=101)])

        results = normalize_product(product, BASE_URL, HEADERS, "Ma Boutique",
                                    steps={"prix": False})
        self.assertEqual(results[0]["prix_apres"], "29.99")

    @patch("features.normalisation.injector._set_product_category")
    @patch("features.normalisation.injector.shopify_put")
    def test_categorie_off_skips_category(self, mock_put, mock_cat):
        mock_put.return_value = {}
        product = _product(pid=1, status="active", variants=[_variant(10.00, vid=1)])

        normalize_product(product, BASE_URL, HEADERS, "Ma Boutique",
                          category_gid="gid://shopify/TaxonomyCategory/aa-1",
                          steps={"categorie": False})
        mock_cat.assert_not_called()


# ── match_category_rule ───────────────────────────────────────────────────────

class TestMatchCategoryRule(unittest.TestCase):

    RULES = [
        {"match": ["armoire"],          "name": "Armoires à bijoux"},
        {"match": ["arbre"],            "name": "Présentoirs à bijoux"},
        {"match": ["porte", "support"], "name": "Support pour bijoux"},
        {"match": ["montre"],           "name": "Boîtes à montres"},
        {"match": ["boite", "coffret"], "name": "Boîtes à bijoux"},
    ]

    def _match(self, title, product_type="", tags=""):
        p = {"title": title, "product_type": product_type, "tags": tags}
        r = match_category_rule(p, self.RULES)
        return r["name"] if r else None

    def test_no_rules_returns_none(self):
        self.assertIsNone(match_category_rule({"title": "X"}, []))

    def test_simple_match(self):
        self.assertEqual(self._match("Armoire à Bijoux Murale LED"), "Armoires à bijoux")

    def test_accents_and_case_insensitive(self):
        self.assertEqual(self._match("ARBRE à bíjoux design"), "Présentoirs à bijoux")

    def test_first_rule_wins_order_priority(self):
        # "Boîte à Montre" contient 'boite' ET 'montre' → 'montre' vient avant 'boite'
        self.assertEqual(self._match("Boîte à Montre Automatique 6 Places"), "Boîtes à montres")

    def test_boite_bijoux_hits_boite_not_montre(self):
        self.assertEqual(self._match("Boîte à Bijoux Bois Élégante"), "Boîtes à bijoux")

    def test_porte_before_montre(self):
        # "Porte Montre" contient 'porte' ET 'montre' → 'porte' vient avant 'montre'
        self.assertEqual(self._match("Porte Montre Mural Bois"), "Support pour bijoux")

    def test_match_on_tags_list(self):
        self.assertEqual(self._match("Rangement Chic", tags=["voyage", "coffret"]), "Boîtes à bijoux")

    def test_match_on_product_type(self):
        self.assertEqual(self._match("Modèle 2024", product_type="Support mural"), "Support pour bijoux")

    def test_no_match_returns_none(self):
        self.assertIsNone(self._match("Bracelet en argent"))

    def test_whole_word_no_false_positive(self):
        # 'arbre' ne doit pas matcher un mot qui le contient sans être le mot
        self.assertIsNone(self._match("Marbrerie décorative"))

    def test_name_used_as_keyword_when_no_match_list(self):
        rules = [{"name": "Boîtes à bijoux"}]
        p = {"title": "Superbe boîtes à bijoux", "product_type": "", "tags": ""}
        self.assertEqual(match_category_rule(p, rules)["name"], "Boîtes à bijoux")

    def test_multiword_keyword_requires_all_words(self):
        # mot-clé "boite montre" → exige boite ET montre présents
        rules = [
            {"match": ["boite montre"], "name": "Boîtes à montres"},
            {"match": ["boite"],        "name": "Boîtes à bijoux"},
        ]
        watch = {"title": "Boîte à Montre 6 Places", "product_type": "", "tags": ""}
        jewel = {"title": "Boîte à Bijoux Bois",     "product_type": "", "tags": ""}
        self.assertEqual(match_category_rule(watch, rules)["name"], "Boîtes à montres")
        self.assertEqual(match_category_rule(jewel, rules)["name"], "Boîtes à bijoux")

    def test_multiword_order_independent(self):
        rules = [{"match": ["montre boite"], "name": "Boîtes à montres"}]
        p = {"title": "Boîte à Montre Automatique", "product_type": "", "tags": ""}
        self.assertEqual(match_category_rule(p, rules)["name"], "Boîtes à montres")


# ── niche_to_match_keywords ────────────────────────────────────────────────────

class TestNicheToMatchKeywords(unittest.TestCase):

    def test_drops_stopwords_and_accents(self):
        self.assertEqual(niche_to_match_keywords("Boîte à Montre"), ["boite montre"])

    def test_single_word(self):
        self.assertEqual(niche_to_match_keywords("Armoire à Bijoux"), ["armoire bijoux"])

    def test_empty(self):
        self.assertEqual(niche_to_match_keywords("  "), [])


# ── suggest_categories_for_niches ──────────────────────────────────────────────

class TestSuggestCategories(unittest.TestCase):

    @patch("features.normalisation.injector.search_taxonomy_categories")
    def test_picks_best_overlap_leaf(self, mock_search):
        mock_search.return_value = [
            {"id": "gid::1", "name": "Bracelets",         "fullName": "Bijoux > Bracelets", "isLeaf": True},
            {"id": "gid::2", "name": "Armoires à bijoux", "fullName": "Rangement > Armoires", "isLeaf": True},
        ]
        rules = suggest_categories_for_niches(["Armoire à Bijoux"], BASE_URL, HEADERS)
        self.assertEqual(len(rules), 1)
        self.assertEqual(rules[0]["name"], "Armoires à bijoux")
        self.assertEqual(rules[0]["gid"], "gid::2")
        self.assertTrue(rules[0]["found"])
        self.assertEqual(rules[0]["match"], ["armoire bijoux"])

    @patch("features.normalisation.injector.search_taxonomy_categories")
    def test_not_found_fallback(self, mock_search):
        mock_search.return_value = []
        rules = suggest_categories_for_niches(["Truc Inconnu"], BASE_URL, HEADERS)
        self.assertFalse(rules[0]["found"])
        self.assertIsNone(rules[0]["gid"])
        self.assertEqual(rules[0]["name"], "Truc Inconnu")

    @patch("features.normalisation.injector.search_taxonomy_categories")
    def test_search_exception_is_safe(self, mock_search):
        mock_search.side_effect = RuntimeError("boom")
        rules = suggest_categories_for_niches(["Armoire"], BASE_URL, HEADERS)
        self.assertFalse(rules[0]["found"])

    @patch("features.normalisation.injector.search_taxonomy_categories")
    def test_sorted_specific_first(self, mock_search):
        mock_search.return_value = [{"id": "g", "name": "X", "fullName": "", "isLeaf": True}]
        rules = suggest_categories_for_niches(["Boîte", "Boîte à Montre Chic"], BASE_URL, HEADERS)
        # "Boîte à Montre Chic" (3 mots) doit passer avant "Boîte" (1 mot)
        counts = [len(r["match"][0].split()) for r in rules]
        self.assertEqual(counts, sorted(counts, reverse=True))


# ── resolve_rule_gids ─────────────────────────────────────────────────────────

class TestResolveRuleGids(unittest.TestCase):

    @patch("features.normalisation.injector.find_taxonomy_category_gid")
    def test_resolves_each_rule(self, mock_find):
        mock_find.side_effect = lambda term, *a: f"gid::{term}"
        rules = [{"match": ["a"], "name": "Cat A"}, {"match": ["b"], "name": "Cat B"}]
        resolve_rule_gids(rules, BASE_URL, HEADERS)
        self.assertEqual(rules[0]["_gid"], "gid::Cat A")
        self.assertEqual(rules[1]["_gid"], "gid::Cat B")

    @patch("features.normalisation.injector.find_taxonomy_category_gid")
    def test_uses_search_over_name(self, mock_find):
        mock_find.side_effect = lambda term, *a: f"gid::{term}"
        rules = [{"name": "Nom FR", "search": "English Term"}]
        resolve_rule_gids(rules, BASE_URL, HEADERS)
        self.assertEqual(rules[0]["_gid"], "gid::English Term")

    @patch("features.normalisation.injector.find_taxonomy_category_gid")
    def test_caches_identical_terms(self, mock_find):
        mock_find.return_value = "gid::x"
        rules = [{"name": "Même"}, {"name": "Même"}]
        resolve_rule_gids(rules, BASE_URL, HEADERS)
        self.assertEqual(mock_find.call_count, 1)   # résolu une seule fois

    @patch("features.normalisation.injector.find_taxonomy_category_gid")
    def test_not_found_sets_none(self, mock_find):
        mock_find.return_value = None
        rules = [{"name": "Introuvable"}]
        resolve_rule_gids(rules, BASE_URL, HEADERS)
        self.assertIsNone(rules[0]["_gid"])

    @patch("features.normalisation.injector.find_taxonomy_category_gid")
    def test_explicit_gid_skips_search(self, mock_find):
        # GID fourni (bouton) → utilisé directement, aucune recherche
        rules = [{"name": "X", "gid": "gid://shopify/TaxonomyCategory/hb-2-3-2"}]
        resolve_rule_gids(rules, BASE_URL, HEADERS)
        self.assertEqual(rules[0]["_gid"], "gid://shopify/TaxonomyCategory/hb-2-3-2")
        mock_find.assert_not_called()


# ── generate_injection_report ─────────────────────────────────────────────────

class TestGenerateInjectionReport(unittest.TestCase):

    def _make_log(self):
        return [
            {"handle": "prod-1", "titre_produit": "Produit 1", "sku": "A",
             "prix_avant": "29.99", "compare_at_avant": "49.99", "prix_apres": "49.99",
             "statut": "OK", "erreur": ""},
            {"handle": "prod-2", "titre_produit": "Produit 2", "sku": "B",
             "prix_avant": "59.99", "compare_at_avant": "", "prix_apres": "59.99",
             "statut": "ERREUR", "erreur": "Timeout"},
        ]

    def test_creates_csv_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            self.assertTrue(os.path.exists(path))

    def test_csv_has_correct_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                reader = csv.DictReader(f)
                fieldnames = reader.fieldnames
            expected = ["date_heure", "handle", "titre_produit", "sku",
                        "prix_avant", "compare_at_avant", "prix_apres", "statut", "erreur"]
            for col in expected:
                self.assertIn(col, fieldnames)

    def test_csv_has_correct_row_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)

    def test_csv_statut_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            statuts = [r["statut"] for r in rows]
            self.assertIn("OK", statuts)
            self.assertIn("ERREUR", statuts)

    def test_filename_contains_timestamp(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            filename = os.path.basename(path)
            self.assertTrue(filename.startswith("normalisation_rapport_"))
            self.assertTrue(filename.endswith(".csv"))

    def test_prix_apres_correct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = generate_injection_report(self._make_log(), tmp)
            with open(path, encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(rows[0]["prix_apres"], "49.99")


if __name__ == "__main__":
    unittest.main()
