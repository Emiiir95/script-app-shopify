#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generator.py — Génération OpenAI pour la feature Collections.

Fonctions publiques :
  - load_keywords_for_collection : filtre keywords.csv pour une collection
  - generate_collection_description : description HTML 1000+ mots
  - generate_collection_meta_title  : meta title 60-70 chars
  - generate_collection_meta_desc   : meta description ~155 chars

Règle fallback : aucune exception ne remonte — toujours retourner du contenu utilisable.
"""

import csv
import json
import os
import re

from features.collections.prompts import (
    build_collection_description_prompt,
    build_collection_meta_title_prompt,
    build_collection_meta_desc_prompt,
)
from utils.logger import log

MODEL_DESC  = "gpt-4o"      # gpt-4o pour la description longue (1000+ mots, structure riche)
MODEL_META  = "gpt-4o-mini" # gpt-4o-mini pour meta title / meta desc (courts, JSON)
TEMP_HIGH   = 0.85
TEMP_LOW    = 0.3


def load_keywords_for_collection(store_path, tags):
    """
    Charge keywords.csv et filtre les mots-clés pertinents pour une collection.

    Stratégie de matching : un keyword est pertinent si au moins un mot du tag
    apparaît dans le keyword (insensible à la casse).

    Args:
        store_path : chemin absolu vers stores/{boutique}/
        tags       : liste de tags de la collection

    Returns:
        str : bloc texte formaté "- keyword (volume)" ou "" si fichier absent
    """
    csv_path = os.path.join(store_path, "seo_boost", "keywords.csv")
    if not os.path.exists(csv_path):
        return ""

    tag_words = set()
    for tag in tags:
        for word in tag.lower().split():
            if len(word) > 2:
                tag_words.add(word)

    matched = []
    try:
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                keyword = row.get("Keyword", "").lower()
                volume  = row.get("Volume", "")
                if any(word in keyword for word in tag_words):
                    try:
                        vol = int(str(volume).replace(",", "").replace(" ", ""))
                    except (ValueError, TypeError):
                        vol = 0
                    matched.append((keyword, vol))
    except Exception as e:
        log(f"Erreur lecture keywords.csv : {e}", "warning")
        return ""

    # Trier par volume desc, garder les 15 meilleurs
    matched.sort(key=lambda x: x[1], reverse=True)
    top = matched[:15]

    if not top:
        return ""

    lines = [f"- {kw} ({vol:,} recherches/mois)" for kw, vol in top]
    return "KEYWORDS SEO PERTINENTS (volume de recherche mensuel) :\n" + "\n".join(lines)


def generate_collection_description(collection_name, niche_keyword, tags,
                                    seo_keywords, openai_client, cost_tracker, max_retries=3):
    """
    Génère la description HTML de la collection (1000+ mots, 8 H2).

    Args:
        collection_name : nom de la collection
        niche_keyword   : mot-clé de niche
        tags            : liste de tags
        seo_keywords    : bloc keywords formaté (peut être vide)
        openai_client   : instance openai.OpenAI
        cost_tracker    : instance CostTracker
        max_retries     : nombre de tentatives

    Returns:
        str : HTML de la description, ou fallback minimal si échec total
    """
    prompt = build_collection_description_prompt(
        collection_name, niche_keyword, tags, seo_keywords
    )

    for attempt in range(max_retries):
        try:
            resp = openai_client.chat.completions.create(
                model=MODEL_DESC,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMP_HIGH,
            )
            cost_tracker.add(resp.usage)
            raw  = resp.choices[0].message.content.strip()
            # Supprime les balises markdown ```html ... ``` que GPT ajoute parfois
            html = re.sub(r'^```[a-zA-Z]*\s*', '', raw)
            html = re.sub(r'\s*```$', '', html).strip()
            if html:
                return html
        except Exception as e:
            log(f"Erreur description collection '{collection_name}' — tentative {attempt+1}/{max_retries} | {e}", "warning")

    fallback = f"<p><strong>{collection_name}</strong> — Collection de {niche_keyword}.</p>"
    log(f"[WARNING] Fallback description pour collection '{collection_name}'", "warning", also_print=True)
    return fallback


def generate_collection_meta_title(collection_name, niche_keyword, tags,
                                   openai_client, cost_tracker, seo_keywords="", max_retries=3):
    """
    Génère le meta title SEO de la collection (60-70 chars).

    Returns:
        str : meta title, ou fallback "{collection_name} | {niche_keyword}"
    """
    prompt = build_collection_meta_title_prompt(collection_name, niche_keyword, tags, seo_keywords)

    for attempt in range(max_retries):
        try:
            resp = openai_client.chat.completions.create(
                model=MODEL_META,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMP_LOW,
                response_format={"type": "json_object"},
            )
            cost_tracker.add(resp.usage)
            data  = json.loads(resp.choices[0].message.content)
            title = data.get("meta_title", "").strip()
            if title:
                return title
        except Exception as e:
            log(f"Erreur meta title collection '{collection_name}' — tentative {attempt+1}/{max_retries} | {e}", "warning")

    fallback = f"{collection_name} | {niche_keyword}"[:70]
    log(f"[WARNING] Fallback meta title pour collection '{collection_name}'", "warning", also_print=True)
    return fallback


def generate_collection_meta_desc(collection_name, niche_keyword, tags,
                                  openai_client, cost_tracker, seo_keywords="", max_retries=3):
    """
    Génère la meta description SEO de la collection (~155 chars).

    Returns:
        str : meta description, ou fallback minimal
    """
    prompt = build_collection_meta_desc_prompt(collection_name, niche_keyword, tags, seo_keywords)

    for attempt in range(max_retries):
        try:
            resp = openai_client.chat.completions.create(
                model=MODEL_META,
                messages=[{"role": "user", "content": prompt}],
                temperature=TEMP_LOW,
                response_format={"type": "json_object"},
            )
            cost_tracker.add(resp.usage)
            data = json.loads(resp.choices[0].message.content)
            desc = data.get("meta_description", "").strip()
            if desc:
                return desc
        except Exception as e:
            log(f"Erreur meta desc collection '{collection_name}' — tentative {attempt+1}/{max_retries} | {e}", "warning")

    fallback = f"Découvrez notre collection {collection_name}. {niche_keyword} de qualité sélectionnés pour vous."
    log(f"[WARNING] Fallback meta desc pour collection '{collection_name}'", "warning", also_print=True)
    return fallback
