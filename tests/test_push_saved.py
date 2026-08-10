#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests — features/push_saved/pusher.py (repush data générée sans OpenAI)."""

import csv
import os
import tempfile
import unittest
from unittest.mock import patch

from features.push_saved.pusher import (
    seo_data_from_row, reviews_from_row, _find_product,
    push_seo_boost, push_reviews, push_fiche_produit,
)
from utils.archive import save_generated

BASE = "http://base"; H = {}


def _write_csv(store_path, name, rows, fields):
    d = os.path.join(store_path, "rapports")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows:
            w.writerow(r)


class TestReconstruction(unittest.TestCase):
    def test_seo_data_from_row(self):
        row = {"h1_nouveau": "Titre H1", "meta_title": "MT", "handle_nouveau": "new-h",
               "meta_description": "MD", "description_html": "<p>desc</p>"}
        d = seo_data_from_row(row)
        self.assertEqual(d["h1"], "Titre H1")
        self.assertEqual(d["handle_nouveau"], "new-h")
        self.assertEqual(d["description_html"], "<p>desc</p>")
        self.assertEqual(d["caracteristique"], "")   # non récupérable

    def test_reviews_from_row(self):
        row = {"rating_global": "4.8", "review_count": "283",
               "review1_title": "Super", "review1_text": "Top produit",
               "review1_author": "Marie L.", "review1_rating": "5",
               "review2_title": "", "review2_text": ""}   # 2e vide → ignoré
        note, reviews = reviews_from_row(row)
        self.assertEqual(note, "<strong>4.8</strong> | 283+ avis vérifiés")
        self.assertEqual(len(reviews), 1)
        self.assertEqual(reviews[0]["titre"], "Super")
        self.assertEqual(reviews[0]["nom_auteur"], "Marie L.")

    def test_find_product_by_alias(self):
        by_handle = {"new-handle": {"id": 1}}
        alias     = {"old-handle": "new-handle", "new-handle": "old-handle"}
        # cherché par l'ancien handle → retrouvé via l'alias
        self.assertEqual(_find_product(by_handle, alias, "old-handle")["id"], 1)
        self.assertIsNone(_find_product(by_handle, alias, "inconnu"))


class TestPushSeoBoost(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        _write_csv(self.tmp, "seo_boost_preview.csv", [
            {"handle_original": "a", "handle_nouveau": "a-seo", "h1_nouveau": "A",
             "meta_title": "TA", "meta_description": "DA", "description_html": "<p>A</p>",
             "titre_original": "", "differentiator": "", "branding_name": ""},
            {"handle_original": "b", "handle_nouveau": "b-seo", "h1_nouveau": "B",
             "meta_title": "TB", "meta_description": "DB", "description_html": "<p>B</p>",
             "titre_original": "", "differentiator": "", "branding_name": ""},
        ], ["handle_original", "handle_nouveau", "titre_original", "h1_nouveau",
            "differentiator", "branding_name", "meta_title", "meta_description", "description_html"])

    @patch("features.push_saved.pusher.inject_product_seo")
    @patch("features.push_saved.pusher.fetch_all_products")
    def test_pushes_matched_products(self, mock_fetch, mock_inject):
        # produit 'a' pas encore SEO (handle d'origine), 'b' déjà SEO (nouveau handle)
        mock_fetch.return_value = [{"id": 1, "handle": "a"}, {"id": 2, "handle": "b-seo"}]
        res = push_seo_boost(self.tmp, BASE, H)
        self.assertEqual(res["pushed"], 2)
        self.assertEqual(res["not_found"], 0)
        self.assertEqual(mock_inject.call_count, 2)

    @patch("features.push_saved.pusher.inject_product_seo")
    @patch("features.push_saved.pusher.fetch_all_products")
    def test_counts_not_found(self, mock_fetch, mock_inject):
        mock_fetch.return_value = [{"id": 1, "handle": "a"}]   # 'b' absent
        res = push_seo_boost(self.tmp, BASE, H)
        self.assertEqual(res["pushed"], 1)
        self.assertEqual(res["not_found"], 1)


class TestPushReviews(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        row = {"handle": "a-seo", "rating_global": "4.8", "review_count": "120"}
        for i in range(1, 9):
            row[f"review{i}_title"]  = f"t{i}" if i <= 3 else ""
            row[f"review{i}_text"]   = f"x{i}" if i <= 3 else ""
            row[f"review{i}_author"] = f"A{i}." if i <= 3 else ""
            row[f"review{i}_rating"] = "5"
        fields = ["handle", "rating_global", "review_count"] + [
            f"review{i}_{k}" for i in range(1, 9) for k in ("title", "text", "author", "rating")]
        _write_csv(self.tmp, "reviews_preview.csv", [row], fields)

    @patch("features.push_saved.pusher.inject_product_reviews")
    @patch("features.push_saved.pusher.missing_review_slots")
    @patch("features.push_saved.pusher.fetch_product_metafields")
    @patch("features.push_saved.pusher.fetch_all_products")
    def test_fills_only_empty_slots(self, mock_fetch, mock_mf, mock_missing, mock_inject):
        mock_fetch.return_value  = [{"id": 9, "handle": "a-seo"}]
        mock_mf.return_value     = {}
        mock_missing.return_value = [1, 2, 3, 4, 5, 6, 7, 8]   # tous vides
        res = push_reviews(self.tmp, BASE, H)
        self.assertEqual(res["pushed"], 1)
        data = mock_inject.call_args.args[1]
        self.assertEqual(len(data["reviews"]), 3)              # 3 avis dispo
        self.assertEqual(data["missing_slots"], [1, 2, 3])

    @patch("features.push_saved.pusher.inject_product_reviews")
    @patch("features.push_saved.pusher.missing_review_slots")
    @patch("features.push_saved.pusher.fetch_product_metafields")
    @patch("features.push_saved.pusher.fetch_all_products")
    def test_skips_when_no_empty_slot(self, mock_fetch, mock_mf, mock_missing, mock_inject):
        mock_fetch.return_value   = [{"id": 9, "handle": "a-seo"}]
        mock_mf.return_value      = {}
        mock_missing.return_value = []                          # déjà 8 avis
        res = push_reviews(self.tmp, BASE, H)
        self.assertEqual(res["pushed"], 0)
        self.assertEqual(res["skipped"], 1)
        mock_inject.assert_not_called()


class TestPushFromArchive(unittest.TestCase):
    """Quand une archive existe, elle est prioritaire (data complète, par ID produit)."""
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    @patch("features.push_saved.pusher.inject_product_seo")
    @patch("features.push_saved.pusher.fetch_all_products")
    def test_seo_prefers_archive_with_caracteristique(self, mock_fetch, mock_inject):
        mock_fetch.return_value = []                   # aucun autre produit en ligne
        save_generated(self.tmp, "seo_boost", [
            {"product": {"id": 10, "handle": "x", "title": "Produit X"},
             "seo_data": {"h1": "H", "meta_title": "T", "meta_description": "D",
                          "description_html": "<p>d</p>", "handle_nouveau": "x-seo",
                          "caracteristique": "Matière: bois"}},
        ])
        res = push_seo_boost(self.tmp, BASE, H)
        self.assertEqual(res["source"], "archive")
        self.assertEqual(res["pushed"], 1)
        seo = mock_inject.call_args.args[1]
        self.assertEqual(seo["caracteristique"], "Matière: bois")   # récupérée !

    @patch("features.push_saved.pusher.inject_product_seo")
    @patch("features.push_saved.pusher.fetch_all_products")
    def test_seo_avoids_existing_store_titles(self, mock_fetch, mock_inject):
        # Produit Y déjà EN LIGNE (hors archive) avec le titre « Boîte Cuir »
        mock_fetch.return_value = [
            {"id": 99, "handle": "y", "title": "Boîte Cuir"},   # existant, hors run
            {"id": 10, "handle": "x", "title": "Boîte Velours"},  # dans l'archive (run)
        ]
        save_generated(self.tmp, "seo_boost", [
            {"product": {"id": 10, "handle": "x", "title": "Boîte Velours"},
             "seo_data": {"h1": "Boîte Cuir", "meta_title": "T", "meta_description": "D",
                          "description_html": "<p>d</p>", "handle_nouveau": "boite-cuir"}},
        ])
        push_seo_boost(self.tmp, BASE, H)
        seo = mock_inject.call_args.args[1]
        self.assertNotEqual(seo["h1"], "Boîte Cuir")   # évite le titre du produit Y existant

    @patch("features.push_saved.pusher.inject_product_fiche")
    def test_fiche_pushable_from_archive(self, mock_inject):
        save_generated(self.tmp, "fiche_produit", [
            {"product": {"id": 5, "handle": "y"},
             "content": {"phrase": "P", "benefices": ["a", "b", "c"],
                         "description1": "Une description longue complète", "description2": "…"}},
        ])
        res = push_fiche_produit(self.tmp, BASE, H)
        self.assertEqual(res["pushed"], 1)
        content = mock_inject.call_args.args[1]
        self.assertEqual(content["description1"], "Une description longue complète")

    def test_fiche_without_archive_returns_note(self):
        res = push_fiche_produit(self.tmp, BASE, H)
        self.assertEqual(res["pushed"], 0)
        self.assertIn("note", res)

    @patch("features.push_saved.pusher.inject_product_reviews")
    @patch("features.push_saved.pusher.missing_review_slots")
    @patch("features.push_saved.pusher.fetch_product_metafields")
    def test_reviews_archive_recomputes_slots(self, mock_mf, mock_missing, mock_inject):
        mock_mf.return_value = {}
        mock_missing.return_value = [3, 4]             # seuls 2 slots vides
        save_generated(self.tmp, "reviews", [
            {"product": {"id": 7, "handle": "z"}, "note_globale": "<strong>4.8</strong>",
             "reviews": [{"note": "5", "titre": "a", "texte": "x", "nom_auteur": "A."},
                         {"note": "5", "titre": "b", "texte": "y", "nom_auteur": "B."},
                         {"note": "5", "titre": "c", "texte": "z", "nom_auteur": "C."}]},
        ])
        res = push_reviews(self.tmp, BASE, H)
        self.assertEqual(res["pushed"], 1)
        data = mock_inject.call_args.args[1]
        self.assertEqual(data["missing_slots"], [3, 4])   # seulement les vides
        self.assertEqual(len(data["reviews"]), 2)


if __name__ == "__main__":
    unittest.main()
