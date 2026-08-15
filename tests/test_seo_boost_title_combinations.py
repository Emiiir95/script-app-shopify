#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
test_seo_boost_title_combinations.py — Validation EXHAUSTIVE de la génération de titres.

But : garantir que, PEU IMPORTE la combinaison de paramètres de titre choisie
(title_style × natural_titles × branding_position × niche_mode × title_attributes),
la génération produit pour CHAQUE produit de CHAQUE niche :
  - un H1 non vide,
  - un H1 unique (→ handle unique, jamais de -1/-2 ajouté par Shopify),
  - un handle unique et non vide,
  - un meta title non vide,
  - en mode thématique : une niche verrouillée sur la liste fournie.

On rejoue FIDÈLEMENT la séquence de titrage du runner (features/seo_boost/runner.py,
boucle produit) en réutilisant les VRAIES fonctions (generate_product_type,
generate_natural_title, generate_differentiator, build_h1, build_meta_title,
pick_theme_branding, generate_ai_branding_name, make_unique_title, generate_handle).
OpenAI est mocké par un faux client déterministe pensé pour le PIRE cas d'unicité
(titres/attributs génériques → collisions maximales → make_unique_title doit trancher).
"""

import json
import re
import unicodedata
import unittest
from itertools import product as iproduct

from features.seo_boost.generator import (
    generate_product_type,
    generate_natural_title,
    generate_differentiator,
    generate_ai_branding_name,
    pick_theme_branding,
    build_h1,
    build_meta_title,
    generate_handle,
)
from features.seo_boost.runner import make_unique_title
from utils.cost_tracker import CostTracker


# ── Faux client OpenAI déterministe ─────────────────────────────────────────────

def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode("ascii").lower()
    return re.sub(r"[^a-z0-9 ]", " ", s)


class _Usage:
    prompt_tokens = 1
    completion_tokens = 1
    total_tokens = 2


class _Msg:
    def __init__(self, content):
        self.content = content


class _Choice:
    def __init__(self, content):
        self.message = _Msg(content)


class _Resp:
    def __init__(self, content):
        self.choices = [_Choice(content)]
        self.usage = _Usage()


class FakeOpenAI:
    """Route les appels selon le prompt. Conçu pour MAXIMISER les collisions de titres
    (h1/differentiator génériques) afin de tester à fond le filet d'unicité."""

    def __init__(self):
        self.chat = self
        self.completions = self
        self._brand_n = 0

    def create(self, **kw):
        content = kw["messages"][0]["content"]
        if isinstance(content, list):               # multimodal (texte + image)
            content = content[0]["text"]

        # 1) Titre naturel (seul appel avec response_format json) → h1 = niche brute
        #    (volontairement générique → deux produits d'une même niche collisionnent).
        if kw.get("response_format"):
            m = re.search(r'NICHE / CAT.GORIE \(mot-cl. principal\) : "([^"]*)"', content)
            niche = m.group(1) if m else "Produit"
            return _Resp(json.dumps({"h1": niche, "meta_title": niche + " pas cher"}))

        # 2) Détection de niche / type (boutique thématique) → classe dans la liste.
        if "Classe ce produit" in content or "Donne UNIQUEMENT le TYPE" in content:
            mt = re.search(r'TITRE FOURNISSEUR : "([^"]*)"', content)
            title = _norm(mt.group(1) if mt else "")
            title_words = set(title.split())
            niches = re.findall(r'^- (.+)$', content, re.M)
            # a) niche dont TOUS les mots sont dans le titre
            for n in niches:
                w = _norm(n).split()
                if w and all(x in title_words for x in w):
                    return _Resp(n)
            # b) sinon niche partageant au moins un mot
            for n in niches:
                if any(x in title_words for x in _norm(n).split()):
                    return _Resp(n)
            return _Resp(niches[0] if niches else (mt.group(1) if mt else "Produit"))

        # 3) Nom de marque IA → unique par appel (évite les retries/doublons + sleeps).
        if "Invente UN nom de mod" in content:
            self._brand_n += 1
            return _Resp(f"Doudy{self._brand_n}")

        # 4) Differentiator (template) → vide = pire cas (h1 = niche seule → collisions).
        return _Resp("")


# ── Rejoue la séquence de titrage du runner (fidèle) ────────────────────────────

def _simulate(products, cfg):
    client = FakeOpenAI()
    tracker = CostTracker()

    title_style       = cfg.get("title_style", "characteristics")
    branding_mode     = cfg.get("branding_mode", "theme")
    branding_names    = cfg.get("brandingNames", [])
    branding_position = cfg.get("branding_position", "start")
    vendor            = cfg.get("vendor", "")
    title_attributes  = cfg.get("title_attributes")
    niche_mode        = (cfg.get("niche_mode") or "fixed").strip().lower()
    niche_keyword     = cfg.get("niche_keyword", "")
    niches            = cfg.get("niches") or []
    natural_titles    = bool(cfg.get("natural_titles", False))

    branding_state = {"used_names": set(), "identity_map": {}, "handle_identity_map": {}}
    used_titles, used_handles = set(), set()
    out = []

    for prod in products:
        product_keyword = prod.get("title", "")
        handle          = prod.get("handle", "")
        supplier        = prod.get("supplier", product_keyword)

        if niche_mode == "thematic":
            niche_kw = generate_product_type(
                product_keyword, supplier, niche_keyword, client, tracker, niches=niches
            )
        else:
            niche_kw = niche_keyword or product_keyword

        if title_style in ("branded", "seo_branded"):
            if branding_mode == "ai":
                branding_name = generate_ai_branding_name(
                    product_keyword, niche_kw, supplier,
                    product_keyword, handle, branding_state, client, tracker,
                )
            else:
                branding_name = pick_theme_branding(
                    product_keyword, handle, branding_names, branding_state
                )
        else:
            branding_name = ""

        differentiator = ""
        if natural_titles:
            h1, meta_title = generate_natural_title(
                product_keyword, supplier, niche_kw, title_attributes,
                branding_name, branding_position, title_style, client, tracker,
            )
        else:
            differentiator = generate_differentiator(
                product_keyword, niche_kw, supplier, "", client, tracker,
                title_attributes=title_attributes,
            )
            h1 = build_h1(branding_name, niche_kw, differentiator, branding_position, title_style)
            meta_title = build_meta_title(niche_kw, differentiator, vendor)

        avoid = []
        while h1 in used_titles and len(avoid) < 2:
            avoid.append(h1)
            if natural_titles:
                h1, meta_title = generate_natural_title(
                    product_keyword, supplier, niche_kw, title_attributes,
                    branding_name, branding_position, title_style, client, tracker,
                    avoid=avoid,
                )
            else:
                differentiator = generate_differentiator(
                    product_keyword, niche_kw, supplier, "", client, tracker,
                    title_attributes=title_attributes, avoid=avoid,
                )
                h1 = build_h1(branding_name, niche_kw, differentiator, branding_position, title_style)
                meta_title = build_meta_title(niche_kw, differentiator, vendor)

        h1 = make_unique_title(h1, product_keyword, used_titles, title_attributes)
        used_titles.add(h1)

        new_handle = generate_handle(h1)
        if new_handle in used_handles:
            base, k = new_handle, 2
            while f"{base}-{k}" in used_handles:
                k += 1
            new_handle = f"{base}-{k}"
        used_handles.add(new_handle)

        out.append({"h1": h1, "meta_title": meta_title, "handle": new_handle, "niche": niche_kw})

    return out


# ── Jeu de données multi-niches (avec doublons pour stresser l'unicité) ─────────

NICHES = ["Doudou", "Doudou Musical", "Veilleuse", "Peluche", "Tapis d'éveil"]

# Chaque niche a plusieurs produits, dont des quasi-identiques (pire cas d'unicité).
PRODUCTS = [
    {"title": "Doudou Lapin Coton Bio Rose",      "handle": "doudou-lapin-rose"},
    {"title": "Doudou Lapin Coton Bio Rose",      "handle": "doudou-lapin-rose-2"},   # doublon exact
    {"title": "Doudou Ours Velours Beige",        "handle": "doudou-ours-beige"},
    {"title": "Doudou Musical Étoile Bleu",       "handle": "doudou-musical-etoile"},
    {"title": "Doudou Musical Étoile Bleu",       "handle": "doudou-musical-etoile-2"}, # doublon exact
    {"title": "Veilleuse Étoile LED Rechargeable","handle": "veilleuse-etoile-led"},
    {"title": "Veilleuse Lune Tactile Blanche",   "handle": "veilleuse-lune"},
    {"title": "Peluche Éléphant Géante Grise",    "handle": "peluche-elephant"},
    {"title": "Peluche Éléphant Géante Grise",    "handle": "peluche-elephant-2"},      # doublon exact
    {"title": "Tapis d'éveil Jungle Musical",     "handle": "tapis-eveil-jungle"},
    {"title": "Tapis d'éveil Jungle Musical",     "handle": "tapis-eveil-jungle-2"},    # doublon exact
]

ALL_ATTRS_OFF = {"commercial_keyword": False, "dimensions": False, "feature": False,
                 "material": False, "style": False, "color": False}


class TestTitleCombinations(unittest.TestCase):
    """Balaie TOUTES les combinaisons de paramètres de titre × multi-niches."""

    def _assert_valid(self, results, cfg, expect_thematic):
        n = len(PRODUCTS)
        self.assertEqual(len(results), n, f"nombre de produits | cfg={cfg}")

        h1s     = [r["h1"] for r in results]
        handles = [r["handle"] for r in results]

        # Tous non vides
        for r in results:
            self.assertTrue(r["h1"].strip(),         f"H1 vide | cfg={cfg} | {r}")
            self.assertTrue(r["handle"].strip(),     f"handle vide | cfg={cfg} | {r}")
            self.assertTrue(r["meta_title"].strip(), f"meta title vide | cfg={cfg} | {r}")

        # Unicité stricte (le cœur de la garantie)
        self.assertEqual(len(set(h1s)), n,      f"H1 non uniques | cfg={cfg} | {h1s}")
        self.assertEqual(len(set(handles)), n,  f"handles non uniques | cfg={cfg} | {handles}")

        # En thématique : chaque niche détectée appartient à la liste
        if expect_thematic:
            for r in results:
                self.assertIn(r["niche"], NICHES, f"niche hors liste | cfg={cfg} | {r}")

    def test_all_combinations(self):
        title_styles      = ["characteristics", "branded", "seo_branded"]
        naturals          = [False, True]
        positions         = ["start", "end"]
        niche_modes       = ["fixed", "thematic"]
        attrs_variants    = [None, ALL_ATTRS_OFF]

        combos = 0
        for ts, nat, pos, nm, attrs in iproduct(
            title_styles, naturals, positions, niche_modes, attrs_variants
        ):
            cfg = {
                "title_style":       ts,
                "natural_titles":    nat,
                "branding_position": pos,
                "branding_mode":     "theme",
                "brandingNames":     ["Nino", "Luna", "Pilou", "Cielo", "Baboo"],
                "niche_mode":        nm,
                "niche_keyword":     "Doudou",
                "niches":            NICHES,
                "vendor":            "Ma Boutique",
                "title_attributes":  attrs,
            }
            results = _simulate(PRODUCTS, cfg)
            self._assert_valid(results, cfg, expect_thematic=(nm == "thematic"))
            combos += 1

        self.assertEqual(combos, 3 * 2 * 2 * 2 * 2)   # 48 combinaisons couvertes

    def test_branding_mode_ai_thematic(self):
        # Le chemin branding IA (appel OpenAI) doit aussi tenir sur toutes les niches.
        for ts in ("branded", "seo_branded"):
            cfg = {
                "title_style":       ts,
                "natural_titles":    False,
                "branding_position": "end",
                "branding_mode":     "ai",
                "niche_mode":        "thematic",
                "niche_keyword":     "Doudou",
                "niches":            NICHES,
                "vendor":            "Ma Boutique",
            }
            results = _simulate(PRODUCTS, cfg)
            self._assert_valid(results, cfg, expect_thematic=True)

    def test_worst_case_200_identical_products_stay_unique(self):
        # 200 produits STRICTEMENT identiques → 200 titres/handles uniques exigés
        # (garantie testée quel que soit le style).
        prods = [{"title": "Doudou Lapin Coton Bio Rose", "handle": f"doudou-{i}"}
                 for i in range(200)]
        for ts in ("characteristics", "seo_branded"):
            cfg = {
                "title_style": ts, "natural_titles": True, "branding_position": "start",
                "branding_mode": "theme", "brandingNames": ["Nino", "Luna"],
                "niche_mode": "thematic", "niche_keyword": "Doudou", "niches": NICHES,
                "vendor": "Ma Boutique", "title_attributes": None,
            }
            results = _simulate(prods, cfg)
            h1s     = [r["h1"] for r in results]
            handles = [r["handle"] for r in results]
            self.assertEqual(len(set(h1s)), 200,     f"H1 non uniques (200) | style={ts}")
            self.assertEqual(len(set(handles)), 200, f"handles non uniques (200) | style={ts}")


if __name__ == "__main__":
    unittest.main()
