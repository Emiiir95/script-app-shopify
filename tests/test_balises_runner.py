#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_balises_runner.py — Test d'INTÉGRATION de la feature Balises.

Exécute le vrai run() de bout en bout (fetch live → classement IA → synchro tags →
PUT) avec Shopify et OpenAI mockés. Vérifie le câblage complet et les tags réellement
envoyés à Shopify. Les utilitaires (backup, lock, checkpoint, rapport) tournent pour de
vrai dans un dossier temporaire.
"""

import json
import re
import tempfile
import unicodedata
import unittest
from unittest.mock import patch, MagicMock

from features.balises import runner as R


SMART_COLLECTIONS = {"smart_collections": [
    {"id": 1, "handle": "doudou",   "title": "Doudou",   "body_html": "Nos doudous",
     "rules": [{"column": "tag", "relation": "equals", "condition": "doudou"}]},
    {"id": 2, "handle": "rose",     "title": "Rose",     "body_html": "",
     "rules": [{"column": "tag", "relation": "equals", "condition": "rose"}]},
    {"id": 3, "handle": "musical",  "title": "Musical",  "body_html": "",
     "rules": [{"column": "tag", "relation": "equals", "condition": "musical"}]},
    {"id": 4, "handle": "prix-bas", "title": "Prix bas", "body_html": "",
     "rules": [{"column": "variant_price", "relation": "less_than", "condition": "50"}]},
]}
PRODUCTS = [
    {"id": 101, "handle": "doudou-lapin",   "title": "Doudou Lapin",    "body_html": "<p>doux</p>",    "product_type": "Doudou",    "tags": "doudou, rose, promo", "status": "active"},
    {"id": 102, "handle": "doudou-musical", "title": "Doudou Musical",  "body_html": "<p>chante</p>",  "product_type": "Doudou",    "tags": "",                   "status": "active"},
    {"id": 103, "handle": "veilleuse",      "title": "Veilleuse Etoile","body_html": "<p>lumiere</p>", "product_type": "Veilleuse", "tags": "veilleuse, rose",    "status": "active"},
    {"id": 104, "handle": "doudou-simple",  "title": "Doudou Simple",   "body_html": "<p>simple</p>",  "product_type": "Doudou",    "tags": "doudou",             "status": "active"},
]


def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]", " ", s).strip()


class _FakeOpenAI:
    """Choisit une collection si son handle apparaît dans le titre du produit."""
    def __init__(self, *a, **k):
        self.chat = self
        self.completions = self

    def create(self, **kw):
        prompt = kw["messages"][0]["content"]
        title  = re.search(r'TITRE : "([^"]*)"', prompt).group(1)
        words  = set(_norm(title).split())
        chosen = [h for h in ("doudou", "rose", "musical") if h in words]
        resp = MagicMock()
        resp.choices = [MagicMock(message=MagicMock(content=json.dumps({"collections": chosen})))]
        resp.usage = MagicMock(prompt_tokens=10, completion_tokens=5, total_tokens=15)
        return resp


class TestBalisesRunnerEndToEnd(unittest.TestCase):
    def setUp(self):
        self.puts = {}

    def _fake_put(self, url, headers, payload):
        self.puts[payload["product"]["id"]] = payload["product"]["tags"]
        return {"product": {"id": payload["product"]["id"]}}

    def _run(self):
        store_path = tempfile.mkdtemp()
        cfg = {"name": "Test", "store_url": "test.myshopify.com",
               "access_token": "shpat_x", "openai_key": "sk-test"}
        with patch.object(R, "OpenAI", _FakeOpenAI), \
             patch.object(R, "ask_product_status", lambda: None), \
             patch.object(R, "fetch_product_metafields", lambda *a, **k: {"caracteristique": ""}), \
             patch("features.balises.injector.shopify_get", lambda *a, **k: SMART_COLLECTIONS), \
             patch("features.balises.injector.shopify_get_paginated", lambda *a, **k: ({"products": PRODUCTS}, "")), \
             patch("features.balises.injector.shopify_put", self._fake_put), \
             patch("builtins.input", lambda *a, **k: "yes"):
            R.run(cfg, store_path)

    def _tags(self, pid):
        return set(_norm(t) for t in self.puts.get(pid, "").split(",") if t.strip())

    def test_end_to_end_reset(self):
        self._run()
        # Remise à plat : chaque produit ne garde QUE les tags des collections choisies.
        # 101 : rose + promo effacés → ne reste que doudou
        self.assertEqual(self._tags(101), {"doudou"})
        # 102 : ajout des deux collections choisies
        self.assertEqual(self._tags(102), {"doudou", "musical"})
        # 103 : aucune collection → TOUS les tags effacés (veilleuse + rose)
        self.assertEqual(self.puts.get(103), "")
        self.assertEqual(self._tags(103), set())
        # 104 : déjà exactement {doudou} → aucun PUT
        self.assertNotIn(104, self.puts)
        # au total, seuls 3 produits modifiés
        self.assertEqual(set(self.puts.keys()), {101, 102, 103})

    def test_no_collections_aborts_without_put(self):
        with patch("features.balises.injector.shopify_get", lambda *a, **k: {"smart_collections": []}), \
             patch.object(R, "OpenAI", _FakeOpenAI), \
             patch.object(R, "ask_product_status", lambda: None), \
             patch("features.balises.injector.shopify_put", self._fake_put):
            R.run({"name": "T", "store_url": "t.myshopify.com",
                   "access_token": "x", "openai_key": "sk-test"}, tempfile.mkdtemp())
        self.assertEqual(self.puts, {})

    def test_failed_product_is_skipped_and_reported(self):
        import csv, glob, os
        # Un client qui ÉCHOUE toujours → classify_product renvoie None → produit ignoré.
        class _Boom:
            def __init__(self, *a, **k):
                self.chat = self; self.completions = self
            def create(self, **kw):
                raise Exception("panne IA")

        store_path = tempfile.mkdtemp()
        with patch.object(R, "OpenAI", _Boom), \
             patch.object(R, "ask_product_status", lambda: None), \
             patch.object(R, "fetch_product_metafields", lambda *a, **k: {"caracteristique": ""}), \
             patch("features.balises.generator.time.sleep", lambda *a: None), \
             patch("features.balises.injector.shopify_get", lambda *a, **k: SMART_COLLECTIONS), \
             patch("features.balises.injector.shopify_get_paginated", lambda *a, **k: ({"products": PRODUCTS}, "")), \
             patch("features.balises.injector.shopify_put", self._fake_put), \
             patch("builtins.input", lambda *a, **k: "yes"):
            R.run({"name": "T", "store_url": "t.myshopify.com",
                   "access_token": "x", "openai_key": "sk-test"}, store_path)

        # Aucun tag écrit (tous les produits ignorés → intacts)
        self.assertEqual(self.puts, {})
        # Un rapport CSV existe et liste les produits ignorés
        reports = glob.glob(os.path.join(store_path, "rapports", "balises_rapport_*.csv"))
        self.assertTrue(reports, "aucun rapport généré")
        with open(reports[0], encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        self.assertEqual(len(rows), len(PRODUCTS))
        self.assertTrue(all(r["statut"] == "IGNORÉ" for r in rows))
        self.assertTrue(all("IA" in r["erreur"] for r in rows))

    def test_missing_openai_key_aborts(self):
        with patch("features.balises.injector.shopify_put", self._fake_put):
            R.run({"name": "T", "store_url": "t.myshopify.com",
                   "access_token": "x", "openai_key": ""}, tempfile.mkdtemp())
        self.assertEqual(self.puts, {})


if __name__ == "__main__":
    unittest.main()
