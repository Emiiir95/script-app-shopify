#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generator.py — Génération du contenu Fiche Produit via OpenAI.

Fonctions publiques :
  - generate_phrase(...)       : phrase d'accroche max 70 chars (gpt-4o-mini, temp 0.5)
  - generate_benefices(...)    : 3 bénéfices courts (gpt-4o, temp 0.5)
  - generate_titres(...)       : 2 titres de sections (gpt-4o-mini, temp 0.5)
  - generate_descriptions(...) : 2 descriptions HTML avec feature-items (gpt-4o-mini, temp 0.5)

Philosophie : aucune fonction ne lève d'exception. En cas d'échec après tous les retries,
une valeur fallback est retournée afin qu'aucun produit ne soit sauté.

Modèles (identiques au transform-boost.js) :
  MODEL_MAIN      = "gpt-4o"       → benefices
  MODEL_SECONDARY = "gpt-4o-mini"  → phrase, titres, descriptions
"""

import re
import time

from features.fiche_produit.prompts import (
    build_phrase_prompt,
    build_benefices_prompt,
    build_titres_prompt,
    build_descriptions_prompt,
)
from utils.logger import log

MODEL_MAIN      = "gpt-4o"
MODEL_SECONDARY = "gpt-4o-mini"

PHRASE_MAX_CHARS   = 70
BENEFIT_MAX_CHARS  = 40


def _clean_html(text):
    """Supprime les balises markdown (```html ... ```) et normalise."""
    if not text:
        return ""
    text = re.sub(r'^```[a-zA-Z]*\s*', '', text.strip())
    text = re.sub(r'\s*```$', '', text).strip()
    return text


def _clean_benefit(text):
    """
    Nettoie un bénéfice. Port exact de cleanBenefit (transform-boost.js) :
    - Supprime balises HTML
    - Supprime guillemets entourants
    - Supprime "..." en fin
    - Supprime tirets/puces en début
    - Tronque à 40 chars au dernier mot
    """
    if not text:
        return ""
    cleaned = re.sub(r'<[^>]+>', '', text).strip()
    cleaned = re.sub(r'^["\']|["\']$', '', cleaned)
    cleaned = re.sub(r'\.{2,}$', '', cleaned)
    cleaned = re.sub(r'^[-•‒–]\s*', '', cleaned).strip()

    if len(cleaned) > BENEFIT_MAX_CHARS:
        truncated  = cleaned[:BENEFIT_MAX_CHARS]
        last_space = truncated.rfind(' ')
        cleaned    = truncated[:last_space] if last_space > 10 else truncated

    return cleaned


def _call_openai(prompt, model, temperature, openai_client, cost_tracker):
    """Appel OpenAI simple, retourne le contenu texte brut."""
    response = openai_client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": prompt}],
        temperature=temperature,
    )
    cost_tracker.add(response.usage)
    return response.choices[0].message.content.strip()


def generate_phrase(product_keyword, niche_keyword, reassurance_points, supplier_description,
                    openai_client, cost_tracker, max_retries=3):
    """
    Génère la phrase d'accroche commerciale.
    La phrase est retournée telle que GPT la génère — aucune troncature.
    En cas d'échec total : retourne product_keyword (jamais d'exception).
    """
    prompt = build_phrase_prompt(product_keyword, niche_keyword, reassurance_points, supplier_description)
    best   = None

    for attempt in range(max_retries):
        try:
            raw    = _call_openai(prompt, MODEL_SECONDARY, 0.5, openai_client, cost_tracker)
            phrase = raw.strip().strip('"\'')

            if phrase:
                best = phrase

            log(f"Phrase OK — {product_keyword!r} | {len(phrase)} chars | coût: ${cost_tracker.cost_usd:.4f}")
            return phrase

        except Exception as e:
            log(f"Phrase retry {attempt+1}/{max_retries} — {product_keyword!r} | {e}", "warning")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    # Fallback : meilleure tentative ou keyword produit
    fallback = best if best else product_keyword
    log(f"Phrase fallback utilisé — {product_keyword!r} | {fallback!r}", "warning", also_print=True)
    return fallback


def generate_benefices(product_keyword, niche_keyword, reassurance_points, supplier_description,
                       openai_client, cost_tracker, max_retries=3):
    """
    Génère 3 bénéfices courts orientés conversion.
    Retourne toujours une liste de 3 strings — fallback par duplication si GPT renvoie moins.
    En cas d'échec total : retourne 3 bénéfices génériques (jamais d'exception).
    """
    prompt = build_benefices_prompt(product_keyword, niche_keyword, reassurance_points, supplier_description)
    best   = None

    for attempt in range(max_retries):
        try:
            raw   = _call_openai(prompt, MODEL_MAIN, 0.5, openai_client, cost_tracker)
            lines = [l for l in raw.split('\n') if l.strip()]
            cleaned = [_clean_benefit(l) for l in lines if _clean_benefit(l)]

            if len(cleaned) >= 3:
                best = cleaned[:3]
                log(f"Bénéfices OK — {product_keyword!r} | {best} | coût: ${cost_tracker.cost_usd:.4f}")
                return best

            # Moins de 3 : on garde et on réessaie
            if cleaned and (best is None or len(cleaned) > len(best)):
                best = cleaned
            raise ValueError(f"Seulement {len(cleaned)} bénéfice(s) reçu(s), 3 attendus.")

        except Exception as e:
            log(f"Bénéfices retry {attempt+1}/{max_retries} — {product_keyword!r} | {e}", "warning")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    # Fallback : compléter avec duplication ou génériques
    if best:
        while len(best) < 3:
            best.append(best[-1])
        log(f"Bénéfices fallback (duplication) — {product_keyword!r} | {best}", "warning", also_print=True)
        return best[:3]

    fallback = ["Qualité premium", "Confort optimal", "Design élégant"]
    log(f"Bénéfices fallback (génériques) — {product_keyword!r}", "warning", also_print=True)
    return fallback


def generate_titres(product_keyword, niche_keyword, reassurance_points, supplier_description,
                    openai_client, cost_tracker, max_retries=3):
    """
    Génère 2 titres de sections accrocheurs.
    Retourne toujours [titre1, titre2] — fallback par duplication si GPT renvoie 1 seul.
    En cas d'échec total : retourne [product_keyword, product_keyword] (jamais d'exception).
    """
    prompt = build_titres_prompt(product_keyword, niche_keyword, reassurance_points, supplier_description)
    best   = None

    for attempt in range(max_retries):
        try:
            raw    = _call_openai(prompt, MODEL_SECONDARY, 0.5, openai_client, cost_tracker)
            text   = _clean_html(raw)
            # Nettoie : retire numérotation (1. / 2. / - / *), guillemets, lignes vides
            import re as _re
            titres = []
            for l in text.split('\n'):
                l = l.strip()
                l = _re.sub(r'^[\d]+[\.\)]\s*', '', l)   # "1. " ou "1) "
                l = _re.sub(r'^[-*•]\s*', '', l)          # "- " ou "* "
                l = l.strip('"\'')
                if l and len(l) > 3:
                    titres.append(l)

            if len(titres) >= 2:
                best = [titres[0], titres[1]]
                log(f"Titres OK — {product_keyword!r} | {best} | coût: ${cost_tracker.cost_usd:.4f}")
                return best

            # 1 titre reçu : on le garde et on réessaie
            if titres and (best is None or not best):
                best = titres
            raise ValueError(f"Seulement {len(titres)} titre(s) reçu(s), 2 attendus.")

        except Exception as e:
            log(f"Titres retry {attempt+1}/{max_retries} — {product_keyword!r} | {e}", "warning")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    # Fallback : dupliquer le seul titre reçu, ou utiliser le keyword
    if best and len(best) >= 1:
        titre = best[0]
        log(f"Titres fallback (duplication) — {product_keyword!r} | {titre!r}", "warning", also_print=True)
        return [titre, titre]

    kw = product_keyword[:60]
    log(f"Titres fallback (keyword) — {product_keyword!r}", "warning", also_print=True)
    return [kw, kw]


def generate_descriptions(product_keyword, reassurance_points, titres, supplier_description,
                          openai_client, cost_tracker, max_retries=3):
    """
    Génère 2 descriptions HTML avec feature-items (séparées par ---SEPARATOR---).
    Retourne toujours [description1, description2] — fallback par duplication si besoin.
    En cas d'échec total : retourne ["", ""] (jamais d'exception).
    """
    prompt = build_descriptions_prompt(product_keyword, reassurance_points, titres, supplier_description)
    best   = None

    for attempt in range(max_retries):
        try:
            raw  = _call_openai(prompt, MODEL_SECONDARY, 0.5, openai_client, cost_tracker)
            text = _clean_html(raw)

            if '---SEPARATOR---' in text:
                parts = text.split('---SEPARATOR---')
                desc1 = parts[0].strip()
                desc2 = parts[1].strip() if len(parts) > 1 else ""

                if desc1 and desc2:
                    log(f"Descriptions OK — {product_keyword!r} | coût: ${cost_tracker.cost_usd:.4f}")
                    return [desc1, desc2]

                if desc1:
                    best = [desc1, desc1]  # duplication si desc2 vide
                raise ValueError("Une des deux descriptions est vide après séparateur.")

            # Pas de séparateur : garder la réponse complète comme meilleure tentative
            if text:
                best = [text, text]
            raise ValueError("Séparateur ---SEPARATOR--- absent de la réponse.")

        except Exception as e:
            log(f"Descriptions retry {attempt+1}/{max_retries} — {product_keyword!r} | {e}", "warning")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    # Fallback : utiliser la meilleure tentative ou chaîne vide
    if best:
        log(f"Descriptions fallback (duplication) — {product_keyword!r}", "warning", also_print=True)
        return best

    log(f"Descriptions fallback (vide) — {product_keyword!r}", "warning", also_print=True)
    return ["", ""]
