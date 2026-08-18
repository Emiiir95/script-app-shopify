#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generator.py — Feature Balises : classement IA d'un produit dans les collections.

classify_product() envoie le contenu du produit + la liste des collections réelles à
OpenAI et retourne la liste des handles de collection choisis (validés contre la liste
fournie — jamais un handle inventé). Repli sur liste vide si l'IA échoue.
"""

import json
import time

from features.balises.prompts import build_classification_prompt
from utils.logger import log

OPENAI_MODEL       = "gpt-4o-mini"   # classement = tâche simple → modèle économique
OPENAI_TEMPERATURE = 0.2             # déterministe : on veut un classement stable


def classify_product(product_ctx, collections, openai_client, cost_tracker,
                     max_collections=0, max_retries=3):
    """
    Détermine les collections d'un produit via OpenAI.

    Args:
        product_ctx     : dict { title, description, product_type, caracteristiques, tags }
        collections     : list de dicts { handle, title, description } — collections réelles
        openai_client   : instance openai.OpenAI
        cost_tracker    : instance CostTracker
        max_collections : plafond par produit (0 = aucun)
        max_retries     : tentatives max

    Returns:
        list[str] : handles de collection choisis, validés (⊆ des handles fournis).
                    Liste VIDE = l'IA a répondu « aucune collection » (cas légitime).
        None      : l'IA a ÉCHOUÉ (réseau/parse) après toutes les tentatives → le
                    runner doit SAUTER le produit (ne pas remettre à plat ses tags).
    """
    if not collections:
        return []

    valid_handles = {c["handle"] for c in collections if c.get("handle")}
    prompt = build_classification_prompt(product_ctx, collections, max_collections)

    for attempt in range(max_retries):
        try:
            resp = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=OPENAI_TEMPERATURE,
                response_format={"type": "json_object"},
            )
            cost_tracker.add(resp.usage)
            data   = json.loads(resp.choices[0].message.content)
            chosen = data.get("collections", []) or []

            # Validation stricte : on ne garde que des handles réels, sans doublon,
            # en préservant l'ordre de l'IA (les plus pertinents d'abord).
            seen, result = set(), []
            for h in chosen:
                h = (h or "").strip()
                if h in valid_handles and h not in seen:
                    seen.add(h)
                    result.append(h)

            # Filet : respecte le plafond même si l'IA l'a dépassé.
            if max_collections and max_collections > 0:
                result = result[:max_collections]

            log(f"Balises — {product_ctx.get('title', '')!r} → {result}")
            return result
        except Exception as e:
            log(f"Erreur classement balises — {product_ctx.get('title', '')!r} | {e} "
                f"(tentative {attempt+1}/{max_retries})", "warning")
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)

    # Échec réel (≠ « aucune collection ») → None : le runner saute le produit et ne
    # touche pas à ses tags (sinon une panne IA effacerait tous les tags du produit).
    log(f"Balises — échec IA pour {product_ctx.get('title', '')!r}, produit ignoré", "warning")
    return None
