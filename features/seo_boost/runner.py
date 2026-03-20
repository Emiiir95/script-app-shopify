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
  title_style           : "branded" | "characteristics"
  branding_mode         : "theme" | "ai"  (ignoré si title_style != "branded")
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
from shopify.products import fetch_all_products_full
from features.seo_boost.generator import (
    strip_html,
    generate_ai_branding_name,
    pick_theme_branding,
    generate_differentiator,
    generate_description,
    generate_meta_description,
    generate_handle,
    build_h1,
    build_meta_title,
)
from features.seo_boost.injector import generate_csv_preview, generate_injection_report, inject_product_seo
from utils.logger import log, LOG_FILE
from utils.cost_tracker import CostTracker, estimate_cost
from utils.checkpoint import save_progress, load_progress, clear_progress

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
    branding_mode = boost_cfg.get("branding_mode", "theme")
    word_count    = max(200, min(400, int(boost_cfg.get("word_count", 200))))

    calls_per = 1  # differentiator — toujours
    inp = _TOKENS_DIFFERENTIATOR[0]
    out = _TOKENS_DIFFERENTIATOR[1]

    if branding_mode == "ai":
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
    'petit', 'grand', 'xxl', 'mini', 'compact',
    'beige', 'noir', 'blanc', 'gris', 'rose', 'bleu', 'rouge', 'vert',
    'marron', 'brun', 'creme', 'taupe', 'anthracite', 'ivoire',
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


def _is_variation_collection(col_name):
    """
    Détermine si une collection est de type VARIATION (taille/couleur).
    Port exact de isVariationCollection (transform-boost.js).
    """
    norm  = _normalize_col_text(col_name)
    words = norm.split()
    return any(w in _VARIATION_KEYWORDS for w in words)


def select_collections_for_product(product_title, supplier_description, boost_cfg):
    """
    Sélectionne les collections pour le maillage interne d'un produit.

    Matching basé sur le TEXTE du produit (titre + description fournisseur),
    pas sur les tags Shopify — plus robuste et 100% générique (toute niche).

    Structure :
      1. mainCollection — TOUJOURS présente (collection principale)
      2. 1 collection TYPE     — matchée par le texte du produit (design, bois, hamac…)
      3. 1 collection VARIATION — matchée par le texte du produit (xxl, beige, petit…)

    Logique de matching : les mots-clés de chaque collection (tags ou nom)
    doivent apparaître dans le contexte produit normalisé.

    Args:
        product_title        : titre du produit Shopify
        supplier_description : description fournisseur (texte brut, sans HTML)
        boost_cfg            : dict seo_boost (mainCollection + collections)

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

    matched_type      = []
    matched_variation = []

    for col in all_collections:
        if not col.get("url"):
            continue

        # Mots-clés de la collection : utilise les tags définis, sinon le nom
        col_tags_raw = col.get("tags") or [col.get("name", "")]
        col_keywords = [_normalize_col_text(t) for t in col_tags_raw if t]

        # Match : au moins un mot-clé de la collection est présent dans le contexte produit
        is_match = any(
            kw and kw in product_context
            for kw in col_keywords
        )
        if not is_match:
            continue

        col_data = {
            "name":   col.get("name", ""),
            "url":    col["url"],
            "volume": col.get("volume", 0),
        }

        # Catégorie : explicite dans config OU auto-détection par nom
        category = col.get("category") or (
            "variation" if _is_variation_collection(col.get("name", "")) else "type"
        )

        if category == "variation":
            matched_variation.append(col_data)
        else:
            matched_type.append(col_data)

    # 2. Meilleure TYPE par volume
    matched_type.sort(key=lambda c: c["volume"], reverse=True)
    if matched_type:
        selected.append(matched_type[0])

    # 3. Meilleure VARIATION par volume
    matched_variation.sort(key=lambda c: c["volume"], reverse=True)
    if matched_variation:
        selected.append(matched_variation[0])

    # Fallbacks si un type manque
    if not matched_type and len(matched_variation) > 1:
        selected.append(matched_variation[1])
    if not matched_variation and len(matched_type) > 1:
        selected.append(matched_type[1])

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

def _generation_phase(products, boost_cfg, all_keywords, openai_client, cost_tracker):
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

    # État partagé pour la détection de variantes couleur (cross-produits)
    branding_state = {
        "used_names":          set(),
        "identity_map":        {},
        "handle_identity_map": {},
    }

    all_products_data = []

    for product in tqdm(products, desc="Génération SEO"):
        product_keyword      = product.get("title", "")
        handle               = product.get("handle", "")
        supplier_description = strip_html(product.get("body_html", ""))
        niche_kw             = niche_keyword or product_keyword

        log(f"Génération SEO — {handle!r} | title: {product_keyword!r}")

        try:
            # ── Keywords matching ─────────────────────────────────────────────
            matched_kws      = match_keywords_to_product(
                product_keyword, supplier_description, all_keywords, niche_kw, boost_cfg
            )
            seo_keywords_block = format_keywords_for_prompt(matched_kws, niche_kw)

            # ── Branding name ─────────────────────────────────────────────────
            if title_style == "branded":
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

            # ── Differentiator → H1 → meta title ─────────────────────────────
            differentiator = generate_differentiator(
                product_keyword, niche_kw, supplier_description,
                seo_keywords_block, openai_client, cost_tracker,
            )
            h1         = build_h1(branding_name, niche_kw, differentiator, branding_position)
            meta_title = build_meta_title(niche_kw, differentiator, vendor)

            # ── Meta description ──────────────────────────────────────────────
            # Utilise le H1 comme productKeyword (identique au JS transform-boost.js)
            meta_description = ""
            if generate_meta_desc:
                meta_description = generate_meta_description(
                    h1, niche_kw, supplier_description,
                    seo_keywords_block, openai_client, cost_tracker,
                )

            # ── Sélection des collections pour le maillage interne ────────────
            selected_collections = select_collections_for_product(product_keyword, supplier_description, boost_cfg)
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

            # ── Handle ────────────────────────────────────────────────────────
            handle_nouveau = generate_handle(h1)

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

    # ── Injection ──
    print("\n[INJ] Injection dans Shopify...")
    log("Début injection SEO Boost")

    last_index, completed_handles = load_progress(store_path)
    if last_index >= 0:
        print(f"[REPRISE] Checkpoint détecté — reprise depuis le produit {last_index + 1}")

    success_count = 0
    fail_count    = 0
    injection_log = []

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
            save_progress(store_path, idx, completed_handles)
            log(f"SUCCÈS — {handle}")
            print(f"  ✓ {handle}")
            injection_log.append({"product": product, "seo_data": seo_data, "statut": "OK"})

        except Exception as e:
            fail_count += 1
            log(f"ÉCHEC — {handle} | {e}", "error", also_print=True)
            print(f"  ✗ {handle} — {e}")
            injection_log.append({"product": product, "seo_data": seo_data, "statut": "ERREUR", "erreur": str(e)})
            continue

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
        clear_progress(store_path)
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
            clear_progress(store_path)
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

    # ── 3. Récupération des produits (avec body_html) ─────────────────────────
    print("\n[3/4] Récupération des produits Shopify...")
    products = fetch_all_products_full(base_url, headers)

    if not products:
        log("Aucun produit trouvé — arrêt.", "error", also_print=True)
        sys.exit(1)

    print(f"[INFO] {len(products)} produit(s) récupérés.")
    _print_seo_boost_estimate(len(products), boost_cfg)

    # ── 4. Génération des données SEO via OpenAI ──────────────────────────────
    print("\n[4/4] Génération SEO via OpenAI...")
    all_products_data = _generation_phase(
        products, boost_cfg, all_keywords, openai_client, cost_tracker
    )

    cost_summary = cost_tracker.summary()
    print(f"\n[OPENAI] {cost_summary}")
    log(f"Coûts OpenAI SEO Boost : {cost_summary}")

    if not all_products_data:
        log("Aucune donnée SEO générée — arrêt.", "error", also_print=True)
        sys.exit(1)

    # ── Sauvegarde du cache ───────────────────────────────────────────────────
    save_seo_boost_cache(store_path, all_products_data, store_config["store_url"])
    log(f"Cache SEO Boost sauvegardé — {len(all_products_data)} produit(s)")

    # ── Phase d'injection ─────────────────────────────────────────────────────
    success = _injection_phase(
        all_products_data, store_path,
        base_url, headers, store_name, cost_tracker,
        generate_meta_desc, generate_desc,
    )
    if success:
        clear_seo_boost_cache(store_path)
