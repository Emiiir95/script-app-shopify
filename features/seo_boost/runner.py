#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration SEO Boost.

Flow :
  1. Charge keywords.csv SEMrush depuis store_path/seo_boost/keywords.csv
  2. Vérifie cache seo_boost_cache.json (reprise possible)
  3. Connexion Shopify + OpenAI
  4. Fetch tous les produits (avec body_html)
  5. Phase de génération : differentiator → H1 → meta title + meta desc + description HTML
  6. Sauvegarde cache seo_boost_cache.json
  7. Preview CSV → confirmation utilisateur
  8. Injection Shopify produit par produit + checkpoint progress.json
  9. Résumé final

Config seo_boost dans config.json :
  niche_keyword         : mot-clé principal de la niche
  title_style           : "characteristics" | "branded" | "seo_branded"
                            - characteristics : niche + SEO complet, sans marque
                            - branded         : marque + niche + SEO court (marque en avant)
                            - seo_branded     : marque + niche + SEO complet
  branding_mode         : "theme" | "ai"  (utilisé si title_style = branded ou seo_branded)
  brandingNames         : list de noms pour le mode theme
  branding_position     : "start" | "end"  (défaut "start")
  vendor                : nom qui apparaît dans le meta title après le |
  word_count            : longueur minimale de la description HTML (défaut: 200)
  generate_meta_description : true | false  (défaut: true)
  generate_description  : true | false  (défaut: true)
"""

import csv
import json
import os
import sys
import time
import unicodedata
import re

from openai import OpenAI
from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from shopify.products import (
    fetch_all_products,
    fetch_all_products_full,
    fetch_all_products_with_images,
    fetch_product_metafields,
    fetch_all_product_metafields,
    set_product_metafield,
)
from features.seo_boost.generator import (
    strip_html,
    generate_ai_branding_name,
    pick_theme_branding,
    generate_differentiator,
    generate_product_type,
    generate_natural_title,
    generate_description,
    generate_meta_description,
    generate_handle,
    generate_specs,
    build_h1,
    build_meta_title,
)
from features.seo_boost.injector import (
    generate_csv_preview, generate_injection_report, inject_product_seo, SEO_BOOST_METAFIELDS,
)
from features.seo_boost.prompts import resolve_title_attributes
from utils.logger import log, LOG_FILE
from utils.cost_tracker import CostTracker, estimate_cost
from utils.checkpoint import save_progress, load_progress, clear_progress
from utils.backup import save_snapshot
from utils.lock import StoreLock
from utils.archive import save_generated
from utils.product_filter import ask_product_status

from datetime import datetime

SEO_BOOST_MODEL = "gpt-4o"

# Tokens moyens estimés par appel OpenAI (mesures empiriques)
_TOKENS_DIFFERENTIATOR = (350, 15)   # (input, output)
_TOKENS_AI_BRANDING    = (220, 8)
_TOKENS_META_DESC      = (450, 60)
_TOKENS_DESC_BASE      = (700, 0)    # output calculé selon word_count


def _print_seo_boost_estimate(n_products, boost_cfg):
    """Affiche l'estimation de coût OpenAI avant la génération."""
    generate_meta = boost_cfg.get("generate_meta_description", True)
    generate_desc = boost_cfg.get("generate_description", True)
    title_style   = boost_cfg.get("title_style", "characteristics")
    branding_mode = boost_cfg.get("branding_mode", "theme")
    word_count    = max(200, min(400, int(boost_cfg.get("word_count", 200))))

    calls_per = 1  # differentiator — toujours
    inp = _TOKENS_DIFFERENTIATOR[0]
    out = _TOKENS_DIFFERENTIATOR[1]

    if title_style in ("branded", "seo_branded") and branding_mode == "ai":
        calls_per += 1
        inp += _TOKENS_AI_BRANDING[0]
        out += _TOKENS_AI_BRANDING[1]

    if generate_meta:
        calls_per += 1
        inp += _TOKENS_META_DESC[0]
        out += _TOKENS_META_DESC[1]

    if generate_desc:
        calls_per += 1
        inp += _TOKENS_DESC_BASE[0]
        out += int(word_count * 1.4)  # ~1.4 tokens/mot en HTML

    total_calls  = calls_per * n_products
    total_input  = inp * n_products
    total_output = out * n_products
    cost         = estimate_cost(SEO_BOOST_MODEL, total_input, total_output)

    print("\n" + "─" * 50)
    print(f"  ESTIMATION COÛT OPENAI — SEO Boost")
    print("─" * 50)
    print(f"  Modèle          : {SEO_BOOST_MODEL}")
    print(f"  Produits        : {n_products}")
    print(f"  Appels estimés  : {total_calls} ({calls_per}/produit)")
    print(f"  Tokens entrée   : ~{total_input:,}")
    print(f"  Tokens sortie   : ~{total_output:,}")
    print(f"  Coût estimé     : ~${cost:.4f} USD")
    print("─" * 50)
    log(
        f"Estimation SEO Boost — {n_products} produits | {total_calls} appels | "
        f"~{total_input:,} tokens in | ~{total_output:,} tokens out | ~${cost:.4f} USD ({SEO_BOOST_MODEL})"
    )


# ── Maillage interne — sélection des collections ─────────────────────────────

# Mots qui classifient une collection comme VARIATION (taille/couleur) vs TYPE (style/forme)
# Port exact de VARIATION_KEYWORDS (transform-boost.js)
_VARIATION_KEYWORDS = {
    'petit', 'petite', 'grand', 'grande', 'xxl', 'mini', 'compact',
    'beige', 'noir', 'blanc', 'gris', 'rose', 'bleu', 'rouge', 'vert',
    'marron', 'brun', 'creme', 'taupe', 'anthracite', 'ivoire',
}

# Mots vides / génériques ignorés lors du matching sur le NOM d'une collection
# (quand aucun tag n'est défini). Complétés dynamiquement par les mots de la
# niche et de la collection principale (voir select_collections_for_product).
_MAILLAGE_STOPWORDS = {
    'a', 'au', 'aux', 'avec', 'ce', 'de', 'des', 'du', 'en', 'et', 'la', 'le',
    'les', 'nos', 'notre', 'par', 'pour', 'sur', 'un', 'une',
    'tout', 'toute', 'toutes', 'tous',
}


def _normalize_col_text(text):
    """Normalise un texte de collection : lowercase + NFKD → ASCII + tirets → espace."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lower      = ascii_text.lower()
    lower      = re.sub(r'[-–]', ' ', lower)
    lower      = re.sub(r'\s+', ' ', lower)
    return lower.strip()


def _parse_tag_set(product_tags):
    """
    Normalise les tags d'un produit Shopify en set de tags normalisés.
    Accepte une chaîne CSV ("A, B, C") — format REST — ou une liste.
    """
    if not product_tags:
        return set()
    raw = product_tags.split(",") if isinstance(product_tags, str) else list(product_tags)
    return {_normalize_col_text(t) for t in raw if t and t.strip()}


def _is_variation_collection(col_name):
    """
    Détermine si une collection est de type VARIATION (taille/couleur).
    Port exact de isVariationCollection (transform-boost.js).
    """
    norm  = _normalize_col_text(col_name)
    words = norm.split()
    return any(w in _VARIATION_KEYWORDS for w in words)


_DIM_RE = re.compile(r'\d+(?:[.,]\d+)?\s*cm', re.IGNORECASE)

# Vocabulaire par catégorie d'attribut (mots NORMALISÉS : sans accent, minuscules).
# Sert à dédoublonner en ne piochant QUE dans les catégories cochées par l'utilisateur.
_COLOR_WORDS = {
    "beige", "noir", "blanc", "gris", "rose", "bleu", "rouge", "vert", "marron", "brun",
    "creme", "taupe", "anthracite", "ivoire", "dore", "argente", "naturel", "fonce",
    "clair", "cuivre", "champagne", "or",
}
_MATERIAL_WORDS = {
    "bois", "cuir", "velours", "metal", "mdf", "bambou", "suede", "marbre", "verre", "tissu",
    "plastique", "resine", "liege", "pu", "acrylique", "feutre", "similicuir", "rotin", "osier",
    "ceramique", "inox", "aluminium",
}
_STYLE_WORDS = {
    "design", "moderne", "elegant", "vintage", "luxe", "minimaliste", "classique", "chic",
    "retro", "scandinave", "boheme",
}
_COMMERCIAL_WORDS = {
    "xxl", "xl", "grand", "grande", "petit", "petite", "mini", "mural", "murale", "plafond",
    "compact", "geant", "geante", "pliable", "rotatif", "portable", "nomade",
}
_GENERIC_ATTR_WORDS = _COLOR_WORDS | _MATERIAL_WORDS | _STYLE_WORDS | _COMMERCIAL_WORDS


def make_unique_title(h1, original_title, used_titles, title_attributes=None):
    """
    Garantit un H1 UNIQUE en respectant les attributs CHOISIS par l'utilisateur.

    GPT génère souvent le même titre générique pour des produits similaires → titres
    (et handles) dupliqués → Shopify ajoute -1/-2. Ici, si `h1` est déjà pris, on greffe
    un détail distinctif du titre fournisseur — mais UNIQUEMENT d'une catégorie ACTIVÉE
    (`title_attributes`). Si l'utilisateur a décoché « couleur » et « dimensions », on ne
    les ajoutera jamais. Dernier recours (produits identiques sur toutes les catégories
    cochées) : suffixe numérique.

    Args:
        h1               : titre H1 généré
        original_title   : titre fournisseur d'origine (contient les détails distinctifs)
        used_titles      : set des H1 déjà attribués (mis à jour par l'appelant)
        title_attributes : dict {clé: bool} des catégories autorisées (None = toutes)

    Returns:
        str : un H1 non encore présent dans used_titles
    """
    if h1 not in used_titles:
        return h1
    attrs    = resolve_title_attributes(title_attributes)
    h1_words = set(_normalize_col_text(h1).split())
    orig     = [w.strip(".,;:()[]") for w in (original_title or "").split()]

    def cat_words(catset):
        return [w for w in orig
                if _normalize_col_text(w) in catset and _normalize_col_text(w) not in h1_words]

    def feature_words():
        out = []
        for w in orig:
            wn = _normalize_col_text(w)
            if (len(wn) >= 3 and wn not in h1_words and wn not in _GENERIC_ATTR_WORDS
                    and wn not in _MAILLAGE_STOPWORDS and not any(ch.isdigit() for ch in wn)):
                out.append(w)
        return out

    # Catégories → extracteurs de tokens distinctifs (ordre de priorité).
    cats = [
        ("dimensions",         lambda: [m.group(0).replace(" ", "") for m in _DIM_RE.finditer(original_title or "")]),
        ("commercial_keyword", lambda: cat_words(_COMMERCIAL_WORDS)),
        ("feature",            feature_words),
        ("material",           lambda: cat_words(_MATERIAL_WORDS)),
        ("style",              lambda: cat_words(_STYLE_WORDS)),
        ("color",              lambda: cat_words(_COLOR_WORDS)),
    ]

    def first_unique(selected):
        for _, extract in selected:
            for c in extract():
                cand = f"{h1} {c}".strip()
                if cand and cand not in used_titles:
                    return cand
        return None

    # 1) D'abord les catégories COCHÉES par l'utilisateur.
    res = first_unique([c for c in cats if attrs.get(c[0])])
    if res:
        return res
    # 2) Dernier recours : catégories DÉCOCHÉES (départage couleur/dimension…) —
    #    uniquement pour les produits sinon strictement identiques.
    res = first_unique([c for c in cats if not attrs.get(c[0])])
    if res:
        return res
    # 3) Vraiment aucun détail distinctif → suffixe numérique.
    n = 2
    while f"{h1} {n}" in used_titles:
        n += 1
    return f"{h1} {n}"


def select_collections_for_product(product_title, supplier_description, boost_cfg, product_tags=None):
    """
    Sélectionne les collections pour le maillage interne d'un produit.

    Matching, par ordre de priorité :
      A. TAGS Shopify du produit (si présents) — source la plus fiable, car les
         smart collections sont construites sur « tag equals {nom de collection} ».
         Une collection est retenue si son nom (ou un de ses tags de config) figure
         dans les tags du produit.
      B. Sinon (produit sans tags) : matching sur le TEXTE (titre + description) —
         mots distinctifs du nom de collection, 100% générique (toute niche).

    Structure du résultat :
      1. mainCollection — TOUJOURS présente (collection principale)
      2. 1 collection TYPE     (design, bois, hamac…)
      3. 1 collection VARIATION (xxl, beige, petit…)

    Args:
        product_title        : titre du produit Shopify
        supplier_description : description fournisseur (texte brut, sans HTML)
        boost_cfg            : dict seo_boost (mainCollection + collections)
        product_tags         : tags Shopify du produit (str CSV ou list) — optionnel

    Returns:
        list : max 3 dicts [{name, url, volume}]
    """
    all_collections = boost_cfg.get("collections", [])
    main_col        = boost_cfg.get("mainCollection")
    selected        = []

    # 1. Collection principale — TOUJOURS
    if main_col and main_col.get("url"):
        selected.append({
            "name":   main_col.get("name", ""),
            "url":    main_col["url"],
            "volume": main_col.get("volume", 0),
        })

    if not all_collections:
        return selected

    # Contexte produit normalisé (titre + description)
    product_context = _normalize_col_text(f"{product_title} {supplier_description}")
    product_words   = set(product_context.split())

    # Mots génériques à ignorer quand on matche sur le NOM d'une collection :
    # les mots de la niche + de la collection principale (ex: "boite", "bijoux")
    # apparaissent partout et ne sont donc pas distinctifs.
    niche_keyword = boost_cfg.get("niche_keyword", "")
    main_name     = main_col.get("name", "") if main_col else ""
    generic_words = _MAILLAGE_STOPWORDS | set(
        _normalize_col_text(f"{niche_keyword} {main_name}").split()
    )

    # Tags Shopify du produit — signal prioritaire (le produit est réellement
    # dans la collection dont le nom = un de ses tags).
    tag_set = _parse_tag_set(product_tags)

    matched_type      = []
    matched_variation = []

    for col in all_collections:
        if not col.get("url"):
            continue

        # A. Correspondance exacte par TAG produit (nom de collection = condition
        #    de la smart collection ; + eventuels tags de config).
        conditions = {_normalize_col_text(col.get("name", ""))}
        for t in (col.get("tags") or []):
            conditions.add(_normalize_col_text(t))
        tag_match = bool(tag_set & {c for c in conditions if c})

        # B. Fallback texte (comble les produits sous-taggés).
        if col.get("tags"):
            col_keywords = [_normalize_col_text(t) for t in col["tags"] if t]
            text_match = any(kw and kw in product_context for kw in col_keywords)
        else:
            distinctive = [
                w for w in _normalize_col_text(col.get("name", "")).split()
                if len(w) >= 3 and w not in generic_words
            ]
            text_match = any(w in product_words for w in distinctive)

        if not (tag_match or text_match):
            continue

        col_data = {
            "name":    col.get("name", ""),
            "url":     col["url"],
            "volume":  col.get("volume", 0),
            "_by_tag": tag_match,   # priorite de tri (interne) : les tags priment
        }

        # Catégorie : explicite dans config OU auto-détection par nom
        category = col.get("category") or (
            "variation" if _is_variation_collection(col.get("name", "")) else "type"
        )

        if category == "variation":
            matched_variation.append(col_data)
        else:
            matched_type.append(col_data)

    # Tri : d'abord les collections confirmées par TAG, puis par volume décroissant.
    sort_key = lambda c: (c["_by_tag"], c["volume"])
    matched_type.sort(key=sort_key, reverse=True)
    matched_variation.sort(key=sort_key, reverse=True)

    # 2. Meilleure TYPE   3. Meilleure VARIATION
    if matched_type:
        selected.append(matched_type[0])
    if matched_variation:
        selected.append(matched_variation[0])

    # Fallbacks si une catégorie manque → prend la 2e de l'autre catégorie
    if not matched_type and len(matched_variation) > 1:
        selected.append(matched_variation[1])
    if not matched_variation and len(matched_type) > 1:
        selected.append(matched_type[1])

    # Nettoie la clé interne de tri
    for c in selected:
        c.pop("_by_tag", None)

    return selected


# ── Cache seo_boost_cache.json ────────────────────────────────────────────────

def _cache_file(store_path):
    """Retourne le chemin du fichier cache SEO Boost."""
    return os.path.join(store_path, "seo_boost_cache.json")


def save_seo_boost_cache(store_path, products_data, store_url=""):
    """
    Sauvegarde les données SEO générées dans le cache.

    Args:
        store_path    : chemin absolu vers le dossier de la boutique
        products_data : liste des dicts produit avec leurs données SEO générées
        store_url     : URL de la boutique (pour vérification à la reprise)
    """
    data = {
        "generated_at":  datetime.now().strftime("%Y-%m-%d %H:%M"),
        "store_url":     store_url,
        "products_data": products_data,
    }
    with open(_cache_file(store_path), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_seo_boost_cache(store_path):
    """
    Charge le cache SEO Boost si présent et valide.

    Returns:
        dict ou None : contenu du cache, ou None si absent/corrompu
    """
    path = _cache_file(store_path)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def clear_seo_boost_cache(store_path):
    """Supprime le fichier cache SEO Boost."""
    path = _cache_file(store_path)
    if os.path.exists(path):
        os.remove(path)


# ── Chargement keywords.csv SEMrush ───────────────────────────────────────────

def load_keywords_csv(store_path):
    """
    Lit le fichier keywords.csv au format SEMrush depuis store_path/seo_boost/keywords.csv.

    Colonnes attendues (variantes acceptées) :
      - Keyword  | keyword  | Mot clé
      - Volume   | volume   | Search Volume
      - Intent   | intent
      - KD       | kd
      - CPC (USD)| cpc

    Filtre : volume > 0 uniquement.

    Args:
        store_path : chemin absolu vers le dossier de la boutique

    Returns:
        list : [{"keyword": str, "volume": int, "intent": str}, ...]
               triée par volume décroissant.
               Retourne liste vide si fichier absent (non bloquant).
    """
    csv_path = os.path.join(store_path, "seo_boost", "keywords.csv")

    if not os.path.exists(csv_path):
        msg = f"[INFO] Fichier keywords.csv absent : {csv_path} — matching SEMrush désactivé."
        log(msg, "warning", also_print=True)
        print(f"\n→ Pour activer le matching SEMrush, créez : {csv_path}")
        print("→ Format : Keyword,Volume,Intent,KD,CPC (USD)")
        return []

    KEYWORD_COLS = {"keyword", "mot clé", "mot-cle"}
    VOLUME_COLS  = {"volume", "search volume"}
    INTENT_COLS  = {"intent"}

    keywords = []
    try:
        with open(csv_path, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)

            # Détecter les noms de colonnes réels
            col_keyword = None
            col_volume  = None
            col_intent  = None

            for raw_col in (reader.fieldnames or []):
                col_lower = raw_col.strip().lower()
                if col_lower in KEYWORD_COLS:
                    col_keyword = raw_col
                elif col_lower in VOLUME_COLS:
                    col_volume = raw_col
                elif col_lower in INTENT_COLS:
                    col_intent = raw_col

            # Fallback : chercher par contenance
            if not col_keyword:
                for raw_col in (reader.fieldnames or []):
                    if "keyword" in raw_col.lower() or "mot" in raw_col.lower():
                        col_keyword = raw_col
                        break
            if not col_volume:
                for raw_col in (reader.fieldnames or []):
                    if "volume" in raw_col.lower():
                        col_volume = raw_col
                        break

            if not col_keyword or not col_volume:
                log("keywords.csv : colonnes Keyword/Volume introuvables — matching désactivé.", "warning", also_print=True)
                return []

            for row in reader:
                kw = row.get(col_keyword, "").strip()
                if not kw:
                    continue
                try:
                    vol = int(float(row.get(col_volume, "0").replace(",", "").strip() or "0"))
                except (ValueError, AttributeError):
                    vol = 0

                if vol <= 0:
                    continue

                intent = ""
                if col_intent:
                    intent = row.get(col_intent, "").strip()

                keywords.append({"keyword": kw, "volume": vol, "intent": intent})

        keywords.sort(key=lambda x: x["volume"], reverse=True)
        log(f"Keywords SEMrush chargés — {len(keywords)} keyword(s) avec volume > 0")

    except Exception as e:
        log(f"Erreur lecture keywords.csv : {e}", "error", also_print=True)
        return []

    return keywords


# ── Normalisation texte ────────────────────────────────────────────────────────

def _normalize_text(text):
    """Normalise un texte : lowercase + NFKD → ASCII + tirets → espace."""
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lower      = ascii_text.lower()
    lower      = re.sub(r'[-–]', ' ', lower)
    lower      = re.sub(r'\s+', ' ', lower)
    return lower.strip()


# ── Système de priorité keywords — port exact de keywords.js ──────────────────

MIN_KEYWORD_VOLUME = 100

# Triggers UNIVERSELS (fonctionnent pour toute niche) — port de UNIVERSAL_TRIGGERS (keywords.js)
_UNIVERSAL_TRIGGERS = {
    1: [
        "xxl", "xxxl", "xl", "grand", "grande", "geant",
        "petit", "petite", "mini", "compact",
        "exterieur", "interieur",
        "solide", "stable", "robuste",
    ],
    2: [
        "design", "moderne", "scandinave", "luxe", "premium", "bois",
        "naturel", "industriel", "vintage", "boheme", "minimaliste",
        "elegant", "chic", "original",
    ],
    3: [],   # 100% niche-spécifique, pas de triggers universels
    4: [
        "beige", "noir", "blanc", "gris", "rose", "bleu", "rouge", "vert",
        "marron", "brun", "creme", "taupe", "anthracite", "ivoire",
        "bordeaux", "turquoise", "kaki", "camel",
    ],
}

# Poids intent (identique au JS)
_INTENT_WEIGHTS = {"C": 1.0, "T": 0.8, "N": 0.3, "I": 0.1}


def _build_priority_levels(boost_cfg):
    """
    Construit les niveaux de priorité en fusionnant les triggers universels
    avec les triggers niche-spécifiques de config.json (priorityTriggers).
    Port exact de buildPriorityLevels (keywords.js).
    """
    config_triggers = boost_cfg.get("priorityTriggers", {})
    return {
        1: {
            "label":    "PRIORITÉ 1 — Type/Usage (OBLIGATOIRE dans le titre)",
            "triggers": _UNIVERSAL_TRIGGERS[1] + [_normalize_text(t) for t in config_triggers.get("1", [])],
        },
        2: {
            "label":    "PRIORITÉ 2 — Style/Matériau (RECOMMANDÉ)",
            "triggers": _UNIVERSAL_TRIGGERS[2] + [_normalize_text(t) for t in config_triggers.get("2", [])],
        },
        3: {
            "label":    "PRIORITÉ 3 — Feature/Forme (si de la place)",
            "triggers": [_normalize_text(t) for t in config_triggers.get("3", [])],
        },
        4: {
            "label":    "PRIORITÉ 4 — Couleur (EN DERNIER uniquement)",
            "triggers": _UNIVERSAL_TRIGGERS[4] + [_normalize_text(t) for t in config_triggers.get("4", [])],
        },
    }


def _get_keyword_priority(kw_norm, niche_words, priority_levels):
    """
    Détermine le niveau de priorité d'un keyword (1-4, 5 si aucun match).
    Port exact de getKeywordPriority (keywords.js).
    """
    diff_words = [w for w in kw_norm.split() if len(w) > 1 and w not in niche_words]
    diff_text  = " ".join(diff_words)

    for level in (1, 2, 3, 4):
        for trigger in priority_levels[level]["triggers"]:
            if trigger in diff_text:
                return level
    return 5


# ── Matching keywords × produit ───────────────────────────────────────────────

def match_keywords_to_product(product_title, supplier_description, all_keywords, niche_keyword, boost_cfg=None, limit=5):
    """
    Trouve les keywords SEMrush les plus pertinents pour un produit.
    Port de getTopKeywordsForContext (keywords.js) — version simplifiée sans inférence.

    Logique :
      1. Filtre volume >= MIN_KEYWORD_VOLUME
      2. Normalise le contexte produit
      3. Matche chaque keyword par overlap de mots
      4. Assigne le niveau de priorité (P1-P4)
      5. Score = volume × intent_weight × (matched/total_diff) × priority_multiplier
      6. Retourne max 2 par niveau, total max {limit}

    Returns:
        list : [{"keyword", "volume", "intent", "priority_level", "priority_label"}]
    """
    if not all_keywords:
        return []

    priority_levels  = _build_priority_levels(boost_cfg or {})
    product_context  = _normalize_text(f"{product_title} {supplier_description}")
    niche_words      = set(_normalize_text(niche_keyword).split())

    _priority_mult = {1: 3.0, 2: 2.0, 3: 1.5, 4: 1.0, 5: 0.5}

    scored = []
    for kw_entry in all_keywords:
        if kw_entry.get("volume", 0) < MIN_KEYWORD_VOLUME:
            continue

        kw_norm    = _normalize_text(kw_entry["keyword"])
        kw_words   = kw_norm.split()
        diff_words = [w for w in kw_words if w not in niche_words and len(w) > 1]

        if not diff_words:
            continue

        matched = sum(1 for w in diff_words if w in product_context)
        if matched == 0:
            continue

        match_ratio      = matched / len(diff_words)
        completion_bonus = 1.5 if match_ratio == 1.0 else 1.0
        intent_char      = (kw_entry.get("intent") or "I").strip()[:1].upper()
        intent_w         = _INTENT_WEIGHTS.get(intent_char, 0.3)
        priority         = _get_keyword_priority(kw_norm, niche_words, priority_levels)
        final_score      = kw_entry["volume"] * match_ratio * completion_bonus * intent_w * _priority_mult[priority]

        scored.append({
            "keyword":        kw_entry["keyword"],
            "volume":         kw_entry["volume"],
            "intent":         kw_entry.get("intent", ""),
            "priority_level": priority,
            "priority_label": priority_levels.get(priority, {}).get("label", "autre"),
            "final_score":    final_score,
        })

    # Trier par priorité puis score
    scored.sort(key=lambda x: (x["priority_level"], -x["final_score"]))

    # Max 2 par niveau de priorité, total max = limit
    result     = []
    per_level  = {}
    for kw in scored:
        lvl = kw["priority_level"]
        if per_level.get(lvl, 0) >= 2:
            continue
        result.append(kw)
        per_level[lvl] = per_level.get(lvl, 0) + 1
        if len(result) >= limit:
            break

    return result


# ── Formatage keywords pour prompt — port exact de formatKeywordsForPrompt ────

def format_keywords_for_prompt(matched_keywords, niche_keyword=""):
    """
    Formate les keywords avec la hiérarchie de priorité pour le prompt.
    Port exact de formatKeywordsForPrompt (keywords.js).

    Args:
        matched_keywords : liste de {"keyword", "volume", "priority_level", "priority_label"}
        niche_keyword    : mot-clé de niche (pour l'exemple STRUCTURE TITRE)

    Returns:
        str : bloc formaté ou chaîne vide si liste vide
    """
    if not matched_keywords:
        return ""

    block = "KEYWORDS AUTORISÉS POUR CE PRODUIT :\n\n"

    # Grouper par niveau
    grouped = {}
    for kw in matched_keywords:
        lvl = kw["priority_level"]
        if lvl not in grouped:
            grouped[lvl] = []
        grouped[lvl].append(kw)

    level_labels = {
        1: "🔥 PRIORITÉ 1 — Type/Usage (OBLIGATOIRE dans le titre)",
        2: "🔥 PRIORITÉ 2 — Style/Matériau (RECOMMANDÉ)",
        3: "🔥 PRIORITÉ 3 — Feature/Forme (si de la place)",
        4: "4️⃣  PRIORITÉ 4 — Couleur (EN DERNIER uniquement)",
    }

    for lvl in (1, 2, 3, 4):
        if lvl not in grouped:
            continue
        block += f"{level_labels[lvl]} :\n"
        for kw in grouped[lvl]:
            block += f'   → "{kw["keyword"]}" ({kw["volume"]} rech/mois)\n'

    niche = niche_keyword or "Produit"
    block += "\n"
    block += "STRUCTURE TITRE OBLIGATOIRE :\n"
    block += "   [Niche] + [P1: type/usage] + [taille] + [P3: feature] + [P2: style] + [P4: couleur]\n"
    block += f'   Ex: "{niche} XXL 180cm Design Beige"\n'
    block += f'   Ex: "{niche} Compact Moderne Noir"\n\n'
    block += "RÈGLES :\n"
    block += "→ Extraire les TERMES DIFFÉRENCIANTS (pas la niche entière)\n"
    block += "→ P1 en PREMIER (juste après la niche), P4 en DERNIER\n"
    block += "→ Ne PAS inventer de keywords absents de la liste\n"
    block += "→ Si aucun P1 n'est applicable, commencer par P2\n"

    return block


# ── Phase de génération ───────────────────────────────────────────────────────

# ── Préservation de la description fournisseur ────────────────────────────────
# Au 1er run, body_html contient la description fournisseur (source de génération).
# Comme SEO Boost écrase body_html par le contenu généré, on sauvegarde l'original
# dans un metafield : les runs suivants régénèrent depuis la vraie source, jamais
# par-dessus le texte déjà généré.
SUPPLIER_DESC_NAMESPACE = "custom"
SUPPLIER_DESC_KEY       = "description_fournisseur"


def resolve_supplier_description(product, base_url, headers):
    """
    Retourne la description fournisseur (texte brut) à utiliser comme source de
    génération, en préservant l'original entre les runs.

    - Si le metafield custom.description_fournisseur existe → on l'utilise
      (source d'origine, même après que body_html ait été écrasé par du SEO).
    - Sinon (1er passage) → body_html EST la source d'origine : on la sauvegarde
      dans le metafield, puis on l'utilise.

    Returns:
        str : description fournisseur en texte brut (sans HTML)
    """
    product_id = product.get("id")
    try:
        metafields = fetch_product_metafields(product_id, base_url, headers)
    except Exception as e:
        # Échec de lecture → repli sur body_html (comportement d'origine)
        log(f"Lecture description_fournisseur échouée ({product.get('handle')!r}) : {e}", "warning")
        return strip_html(product.get("body_html", ""))

    backup = (metafields.get(SUPPLIER_DESC_KEY) or "").strip()
    if backup:
        return strip_html(backup)

    # 1er passage : body_html = description fournisseur d'origine → sauvegarde
    original_html = product.get("body_html", "") or ""
    if original_html.strip():
        try:
            set_product_metafield(
                product_id, SUPPLIER_DESC_NAMESPACE, SUPPLIER_DESC_KEY,
                original_html, "multi_line_text_field", base_url, headers,
            )
            log(f"Description fournisseur sauvegardée — {product.get('handle')!r}")
        except Exception as e:
            log(f"Sauvegarde description_fournisseur échouée ({product.get('handle')!r}) : {e}", "warning")
    return strip_html(original_html)


def _generation_phase(products, boost_cfg, all_keywords, openai_client, cost_tracker, base_url, headers):
    """
    Génère les données SEO pour chaque produit via OpenAI.

    Pour chaque produit :
      1. Match keywords SEMrush
      2. Sélectionne ou génère le nom branding
      3. Génère le differentiator via OpenAI
      4. Construit H1 et meta title algorithmiquement
      5. Génère meta description (si activée)
      6. Génère description HTML (si activée)
      7. Génère le handle via slugify

    Args:
        products      : liste de dicts Shopify produit
        boost_cfg     : dict de config seo_boost
        all_keywords  : liste de keywords SEMrush
        openai_client : instance openai.OpenAI
        cost_tracker  : instance CostTracker

    Returns:
        list : all_products_data — liste de dicts {"product": ..., "seo_data": ...}
    """
    niche_keyword      = boost_cfg.get("niche_keyword", "")
    title_style        = boost_cfg.get("title_style", "characteristics")
    branding_mode      = boost_cfg.get("branding_mode", "theme")
    branding_names     = boost_cfg.get("brandingNames", [])
    branding_position  = boost_cfg.get("branding_position", "start")
    vendor             = boost_cfg.get("vendor", "")
    generate_meta_desc = boost_cfg.get("generate_meta_description", True)
    generate_desc      = boost_cfg.get("generate_description", True)
    word_count         = boost_cfg.get("word_count", 200)
    title_attributes   = boost_cfg.get("title_attributes")   # cases à cocher du titre (None = tout)
    niche_mode         = (boost_cfg.get("niche_mode") or "fixed").strip().lower()  # fixed | thematic
    niches             = boost_cfg.get("niches") or []       # liste des niches (mode thématique)
    natural_titles     = bool(boost_cfg.get("natural_titles", False))  # H1 naturel IA vs template
    title_use_image    = bool(boost_cfg.get("title_use_image", False))  # envoyer la 1ère photo à l'IA

    # État partagé pour la détection de variantes couleur (cross-produits)
    branding_state = {
        "used_names":          set(),
        "identity_map":        {},
        "handle_identity_map": {},
    }

    all_products_data = []
    used_titles  = set()   # anti-doublon de titre (→ handles uniques, pas de -1/-2 Shopify)
    used_handles = set()

    # Amorçage anti-doublon PAR BOUTIQUE : on injecte les titres/handles des produits
    # DÉJÀ en ligne qui ne sont PAS dans ce run → les nouveaux produits (run partiel,
    # ajout ultérieur) éviteront les titres existants. On exclut les produits du run
    # en cours pour ne pas les bloquer avec leur propre ancien titre.
    batch_ids = {p.get("id") for p in products}
    try:
        for existing in fetch_all_products(base_url, headers):
            if existing.get("id") not in batch_ids:
                if existing.get("title"):
                    used_titles.add(existing["title"])
                if existing.get("handle"):
                    used_handles.add(existing["handle"])
        if used_titles:
            log(f"Anti-doublon amorcé avec {len(used_titles)} titre(s) déjà en ligne")
    except Exception as e:
        log(f"Amorçage anti-doublon (titres existants) échoué : {e}", "warning")

    for product in tqdm(products, desc="Génération SEO"):
        product_keyword      = product.get("title", "")
        handle               = product.get("handle", "")
        # Source = description fournisseur préservée (metafield) si dispo, sinon
        # body_html d'origine (qu'on sauvegarde alors pour les runs suivants).
        supplier_description = resolve_supplier_description(product, base_url, headers)
        # Base du titre : soit la niche fixe (mono-niche), soit le TYPE réel détecté
        # par l'IA depuis la description (boutique thématique) — ex: "Boîte à Montre".
        if niche_mode == "thematic":
            niche_kw = generate_product_type(
                product_keyword, supplier_description, niche_keyword,
                openai_client, cost_tracker, niches=niches,
            )
        else:
            niche_kw = niche_keyword or product_keyword

        log(f"Génération SEO — {handle!r} | title: {product_keyword!r}")

        try:
            # ── Keywords matching ─────────────────────────────────────────────
            matched_kws      = match_keywords_to_product(
                product_keyword, supplier_description, all_keywords, niche_kw, boost_cfg
            )
            seo_keywords_block = format_keywords_for_prompt(matched_kws, niche_kw)

            # ── Branding name ─────────────────────────────────────────────────
            # Les modes "branded" et "seo_branded" ont tous deux un nom de marque.
            if title_style in ("branded", "seo_branded"):
                if branding_mode == "ai":
                    branding_name = generate_ai_branding_name(
                        product_keyword, niche_kw, supplier_description,
                        product_keyword, handle, branding_state,
                        openai_client, cost_tracker,
                    )
                else:  # theme
                    branding_name = pick_theme_branding(
                        product_keyword, handle, branding_names, branding_state
                    )
            else:
                branding_name = ""

            # 1ère photo (option : l'IA la « voit » pour un titre plus juste — couleur, forme)
            first_image = ""
            if title_use_image:
                imgs = product.get("images") or []
                first_image = (imgs[0].get("src") or "") if imgs else ""

            # ── H1 + meta title : mode NATUREL (IA) ou TEMPLATE (niche + attributs) ──
            differentiator = ""   # inutilisé en mode naturel
            if natural_titles:
                h1, meta_title = generate_natural_title(
                    product_keyword, supplier_description, niche_kw, title_attributes,
                    branding_name, branding_position, title_style, openai_client, cost_tracker,
                    seo_keywords=seo_keywords_block, image_url=first_image,
                )
            else:
                differentiator = generate_differentiator(
                    product_keyword, niche_kw, supplier_description,
                    seo_keywords_block, openai_client, cost_tracker,
                    title_attributes=title_attributes,
                )
                h1 = build_h1(branding_name, niche_kw, differentiator, branding_position, title_style)
                meta_title = build_meta_title(niche_kw, differentiator, vendor)

            # ── Titre UNIQUE ──────────────────────────────────────────────────
            # 1) L'IA d'abord : si le titre est déjà pris, on redemande une variante distincte.
            avoid_titles = []
            while h1 in used_titles and len(avoid_titles) < 2:
                avoid_titles.append(h1)
                if natural_titles:
                    h1, meta_title = generate_natural_title(
                        product_keyword, supplier_description, niche_kw, title_attributes,
                        branding_name, branding_position, title_style, openai_client, cost_tracker,
                        avoid=avoid_titles, seo_keywords=seo_keywords_block, image_url=first_image,
                    )
                else:
                    differentiator = generate_differentiator(
                        product_keyword, niche_kw, supplier_description,
                        seo_keywords_block, openai_client, cost_tracker,
                        title_attributes=title_attributes, avoid=avoid_titles,
                    )
                    h1 = build_h1(branding_name, niche_kw, differentiator, branding_position, title_style)
                    meta_title = build_meta_title(niche_kw, differentiator, vendor)
            # 2) Filet déterministe si l'IA n'a pas suffi (produits quasi identiques)
            h1 = make_unique_title(h1, product_keyword, used_titles, title_attributes)
            used_titles.add(h1)

            # ── Meta description ──────────────────────────────────────────────
            # Utilise le H1 comme productKeyword (identique au JS transform-boost.js)
            meta_description = ""
            if generate_meta_desc:
                meta_description = generate_meta_description(
                    h1, niche_kw, supplier_description,
                    seo_keywords_block, openai_client, cost_tracker,
                )

            # ── Sélection des collections pour le maillage interne ────────────
            selected_collections = select_collections_for_product(
                product_keyword, supplier_description, boost_cfg, product.get("tags")
            )
            if selected_collections:
                col_names = " → ".join(c["name"] for c in selected_collections)
                log(f"Maillage ({len(selected_collections)} lien(s)) : {col_names}")

            # ── Description HTML ──────────────────────────────────────────────
            description_html = ""
            if generate_desc:
                description_html = generate_description(
                    h1, niche_kw, supplier_description,
                    branding_name, word_count, openai_client, cost_tracker,
                    seo_keywords=seo_keywords_block,
                    collections=selected_collections,
                )

            # ── Caractéristiques techniques ───────────────────────────────────
            # Générées ici car supplier_description = body_html original (avant écrasement SEO)
            caracteristique = generate_specs(product_keyword, supplier_description, openai_client, cost_tracker)

            # ── Handle unique (le titre a déjà été rendu unique plus haut) ────
            handle_nouveau = generate_handle(h1)
            if handle_nouveau in used_handles:           # sécurité slug (accents, etc.)
                base, k = handle_nouveau, 2
                while f"{base}-{k}" in used_handles:
                    k += 1
                handle_nouveau = f"{base}-{k}"
            used_handles.add(handle_nouveau)

            all_products_data.append({
                "product": product,
                "seo_data": {
                    "h1":               h1,
                    "meta_title":       meta_title,
                    "handle_nouveau":   handle_nouveau,
                    "meta_description": meta_description,
                    "description_html": description_html,
                    "branding_name":    branding_name,
                    "differentiator":   differentiator,
                    "caracteristique":  caracteristique,
                },
            })

            log(f"Génération OK — {handle!r} | h1: {h1!r} | handle_nouveau: {handle_nouveau!r}")

        except Exception as e:
            log(f"ÉCHEC génération — {handle!r} | {e}", "error", also_print=True)
            print(f"  ✗ {handle} — génération échouée : {e}")
            continue

    return all_products_data


# ── Phase d'injection ─────────────────────────────────────────────────────────

def _injection_phase(all_products_data, store_path, base_url, headers, store_name, cost_tracker, generate_meta_desc, generate_desc):
    """
    Phase finale : CSV → validation utilisateur → injection Shopify → résumé.

    Args:
        all_products_data : liste de dicts {"product": ..., "seo_data": ...}
        store_path        : chemin absolu vers le dossier de la boutique
        base_url          : URL de base REST Shopify
        headers           : dict des headers HTTP Shopify
        store_name        : nom affiché dans le résumé
        cost_tracker      : instance CostTracker
        generate_meta_desc: bool — si True, injecte aussi la meta description
        generate_desc     : bool — si True, injecte aussi la description HTML

    Returns:
        bool : True si tous les produits ont été injectés sans erreur
    """
    # ── CSV preview ──
    print("\n[GEN] Génération du CSV preview...")
    generate_csv_preview(all_products_data, store_path)

    # ── Validation utilisateur ──
    print("\n" + "=" * 60)
    answer = input("Valider l'import Shopify ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Import SEO Boost annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée dans Shopify.")
        return False

    # ── Snapshot avant écrasement (retour en arrière possible) ──
    # On sauvegarde title/handle/body_html ET l'état AVANT des metafields écrits par
    # SEO Boost (meta title/desc, caractéristiques) → le rollback peut les restaurer/supprimer.
    try:
        for e in all_products_data:
            p = e["product"]
            try:
                existing = fetch_all_product_metafields(p["id"], base_url, headers)
                by_key   = {(m.get("namespace"), m.get("key")): m for m in existing}
                p["_metafields_backup"] = [
                    {
                        "namespace": ns, "key": key,
                        "value": by_key[(ns, key)].get("value") if (ns, key) in by_key else None,
                        "type":  by_key[(ns, key)].get("type")  if (ns, key) in by_key else None,
                    }
                    for ns, key in SEO_BOOST_METAFIELDS
                ]
            except Exception as ex:
                log(f"Snapshot metafields échoué ({p.get('handle')!r}) : {ex}", "warning")
                p["_metafields_backup"] = []

        snap_path = save_snapshot(
            store_path, "seo_boost",
            [e["product"] for e in all_products_data],
            ["title", "handle", "body_html", "_metafields_backup"],
        )
        print(f"[BACKUP] État d'origine sauvegardé → {snap_path}")
        log(f"Snapshot SEO Boost créé : {snap_path}")
    except Exception as e:
        log(f"Échec création snapshot SEO Boost : {e}", "warning", also_print=True)

    # ── Injection ──
    print("\n[INJ] Injection dans Shopify...")
    log("Début injection SEO Boost")

    last_index, completed_handles = load_progress(store_path, "seo_boost")
    if last_index >= 0:
        print(f"[REPRISE] Checkpoint détecté — reprise depuis le produit {last_index + 1}")

    success_count = 0
    fail_count    = 0
    injection_log = []

    # Verrou boutique : sérialise les écritures si plusieurs features tournent en parallèle.
    store_lock = StoreLock(store_path, "seo_boost")
    store_lock.acquire(wait_message="  ⏳ Une autre feature ({feature}) écrit sur Shopify — attente de son tour...")
    try:
        for idx, entry in enumerate(tqdm(all_products_data, desc="Produits injectés")):
            product  = entry["product"]
            seo_data = entry["seo_data"]
            handle   = product.get("handle", "")

            if handle in completed_handles:
                log(f"Skip (déjà injecté) : {handle}")
                continue

            print(f"\n  → {handle} ({idx+1}/{len(all_products_data)})")
            log(f"Injection {idx+1}/{len(all_products_data)} : {handle}")

            try:
                inject_product_seo(
                    product,
                    seo_data,
                    base_url,
                    headers,
                    generate_meta_desc=generate_meta_desc,
                    generate_description=generate_desc,
                )
                success_count += 1
                completed_handles.append(handle)
                save_progress(store_path, idx, completed_handles, "seo_boost")
                log(f"SUCCÈS — {handle}")
                print(f"  ✓ {handle}")
                injection_log.append({"product": product, "seo_data": seo_data, "statut": "OK"})

            except Exception as e:
                fail_count += 1
                log(f"ÉCHEC — {handle} | {e}", "error", also_print=True)
                print(f"  ✗ {handle} — {e}")
                injection_log.append({"product": product, "seo_data": seo_data, "statut": "ERREUR", "erreur": str(e)})
                continue
    finally:
        store_lock.release()

    # ── Rapport post-injection ──
    if injection_log:
        generate_injection_report(injection_log, store_path)

    # ── Résumé ──
    log(
        f"Terminé SEO Boost | Succès: {success_count} | Échecs: {fail_count} | "
        f"{cost_tracker.summary()}"
    )
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique      : {store_name}")
    print(f"  Produits OK   : {success_count}")
    print(f"  Produits KO   : {fail_count}")
    if cost_tracker.calls > 0:
        print(f"  OpenAI        : {cost_tracker.calls} appels | ${cost_tracker.cost_usd:.4f} USD")
    print(f"  Logs          : {LOG_FILE}")
    print("=" * 60)

    if fail_count == 0:
        clear_progress(store_path, "seo_boost")
        log("Progression effacée — tous les produits SEO Boost traités.")

    return fail_count == 0


# ── Point d'entrée ────────────────────────────────────────────────────────────

def run(store_config, store_path):
    """
    Point d'entrée de la feature SEO Boost.

    Args:
        store_config : dict avec clés name, store_url, access_token, openai_key
        store_path   : chemin absolu vers le dossier de la boutique (stores/{nom}/)
    """
    store_name = store_config.get("name", "boutique")
    boost_cfg  = store_config.get("seo_boost", {})

    log("=" * 60)
    log(f"Démarrage feature SEO Boost — boutique : {store_name}")
    print("=" * 60)
    print(f"  SEO Boost — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    cost_tracker       = CostTracker(model="gpt-4o")
    generate_meta_desc = boost_cfg.get("generate_meta_description", True)
    generate_desc      = boost_cfg.get("generate_description", True)

    # ── Vérification du cache de génération ──────────────────────────────────
    cached = load_seo_boost_cache(store_path)
    if cached:
        n_cached  = len(cached.get("products_data", []))
        cached_at = cached.get("generated_at", "date inconnue")

        print(f"\n[CACHE] {n_cached} produit(s) déjà générés le {cached_at}, en attente d'injection.")
        print("  (r) Reprendre depuis l'injection  — sans relancer OpenAI")
        print("  (n) Regénérer depuis le début     — efface le cache")
        print("  (q) Annuler")
        choice = input("\nChoix : ").strip().lower()

        if choice == "r":
            log(f"Reprise depuis le cache SEO Boost — {n_cached} produit(s) | généré le {cached_at}")
            print(f"\n[REPRISE] Connexion Shopify — {store_config['store_url']}")
            base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
            headers  = shopify_headers(store_config["access_token"])

            success = _injection_phase(
                cached["products_data"], store_path,
                base_url, headers, store_name, cost_tracker,
                generate_meta_desc, generate_desc,
            )
            if success:
                clear_seo_boost_cache(store_path)
            return

        elif choice == "n":
            clear_seo_boost_cache(store_path)
            clear_progress(store_path, "seo_boost")
            print("[INFO] Cache effacé — reprise depuis le début.\n")

        else:
            print("[ANNULÉ]")
            return

    # ── 1. Chargement keywords SEMrush (non bloquant) ─────────────────────────
    print("\n[1/4] Chargement du fichier keywords.csv (SEMrush)...")
    all_keywords = load_keywords_csv(store_path)
    if all_keywords:
        print(f"[INFO] {len(all_keywords)} keyword(s) chargés.")
    else:
        print("[INFO] Aucun keyword SEMrush — génération sans matching.")

    # ── 2. Initialisation clients ─────────────────────────────────────────────
    print(f"\n[2/4] Connexion — {store_config['store_url']}")
    log(f"Session SEO Boost — store: {store_config['store_url']} | API: {SHOPIFY_API_VERSION}")

    base_url      = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers       = shopify_headers(store_config["access_token"])
    openai_client = OpenAI(api_key=store_config["openai_key"])

    # ── 3. Récupération des produits (avec body_html ; + images si titre par image) ──
    product_status = ask_product_status()
    print("\n[3/4] Récupération des produits Shopify...")
    if boost_cfg.get("natural_titles") and boost_cfg.get("title_use_image"):
        products = fetch_all_products_with_images(base_url, headers, status=product_status)
    else:
        products = fetch_all_products_full(base_url, headers, status=product_status)

    if not products:
        log("Aucun produit trouvé — arrêt.", "error", also_print=True)
        sys.exit(1)

    print(f"[INFO] {len(products)} produit(s) récupérés.")
    _print_seo_boost_estimate(len(products), boost_cfg)

    # ── 4. Génération des données SEO via OpenAI ──────────────────────────────
    print("\n[4/4] Génération SEO via OpenAI...")
    all_products_data = _generation_phase(
        products, boost_cfg, all_keywords, openai_client, cost_tracker, base_url, headers
    )

    cost_summary = cost_tracker.summary()
    print(f"\n[OPENAI] {cost_summary}")
    log(f"Coûts OpenAI SEO Boost : {cost_summary}")

    if not all_products_data:
        log("Aucune donnée SEO générée — arrêt.", "error", also_print=True)
        sys.exit(1)

    # ── Sauvegarde du cache (reprise) + archive permanente (re-poussable) ─────
    save_seo_boost_cache(store_path, all_products_data, store_config["store_url"])
    log(f"Cache SEO Boost sauvegardé — {len(all_products_data)} produit(s)")
    try:
        arch = save_generated(store_path, "seo_boost", all_products_data, store_config["store_url"])
        log(f"Archive SEO Boost (permanente) : {arch}")
    except Exception as e:
        log(f"Échec archive SEO Boost : {e}", "warning")

    # ── Phase d'injection ─────────────────────────────────────────────────────
    success = _injection_phase(
        all_products_data, store_path,
        base_url, headers, store_name, cost_tracker,
        generate_meta_desc, generate_desc,
    )
    if success:
        clear_seo_boost_cache(store_path)
