#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generator.py — Génération des données SEO via OpenAI pour la feature SEO Boost.

Fonctions publiques :
  - strip_html(html_text)                        : supprime les balises HTML
  - slugify(text)                                : convertit en handle Shopify valide
  - generate_meta_description(...)               : génère la meta description via GPT (JSON)
  - generate_handle(h1_title)                    : génère le handle via slugify (pas d'appel OpenAI)
  - extract_product_identity(title)              : normalise un titre produit (sans couleurs)
  - extract_handle_identity(handle)              : normalise un handle (sans couleurs)
  - levenshtein_distance(a, b)                   : distance d'édition entre deux chaînes
  - similarity(a, b)                             : similarité 0-1 entre deux chaînes
  - clean_differentiator(niche_keyword, diff)    : filtre les mots de niche du differentiator
  - build_h1(branding_name, niche_keyword, diff) : construit le H1 algorithmiquement
  - build_meta_title(niche_keyword, diff, vendor): construit le meta title algorithmiquement
  - pick_theme_branding(title, handle, pool, state): sélectionne un nom branding depuis un pool
  - generate_ai_branding_name(...)               : génère/réutilise un nom branding via GPT
  - generate_differentiator(...)                 : génère les attributs différenciants via GPT
  - generate_description(...)                    : génère la description HTML via GPT
"""

import json
import re
import time
import unicodedata

from features.seo_boost.prompts import (
    build_boost_ai_branding_prompt,
    build_boost_meta_prompt,
    build_boost_differentiator_prompt,
    build_boost_description_prompt,
)
from utils.logger import log

OPENAI_MODEL       = "gpt-4o"
OPENAI_TEMPERATURE = 0.85
OPENAI_TEMPERATURE_LOW = 0.4

SIMILARITY_THRESHOLD = 0.85

COLOR_WORDS = [
    'beige', 'noir', 'blanc', 'gris', 'rose', 'bleu', 'rouge', 'vert',
    'jaune', 'orange', 'violet', 'marron', 'brun', 'creme', 'ivoire',
    'taupe', 'anthracite', 'bordeaux', 'turquoise', 'corail', 'saumon',
    'kaki', 'camel', 'caramel', 'chocolat', 'cognac', 'lavande', 'menthe',
    'moutarde', 'olive', 'peche', 'prune', 'rouille', 'sable', 'terracotta',
    'fuchsia', 'magenta', 'cyan', 'indigo', 'lilas', 'mauve',
    'dore', 'argente', 'cuivre', 'multicolore', 'bicolore', 'tricolore',
    'black', 'white', 'grey', 'gray', 'pink', 'blue', 'red', 'green',
    'yellow', 'brown', 'cream', 'ivory', 'navy', 'teal', 'coral',
    'khaki', 'gold', 'silver', 'copper',
]

SIZE_ADJECTIVES = {'petit', 'petite', 'mini', 'compact', 'grand', 'grande', 'geant'}

STYLE_COULEUR = {
    'design', 'moderne', 'scandinave', 'luxe', 'premium', 'naturel',
    'industriel', 'vintage', 'boheme', 'minimaliste', 'elegant', 'chic',
    'original', 'modulable',
    'beige', 'noir', 'blanc', 'gris', 'rose', 'bleu', 'rouge', 'vert',
    'marron', 'brun', 'creme', 'taupe', 'anthracite', 'ivoire',
    'bordeaux', 'turquoise', 'kaki', 'camel',
}


def _normalize_str(s):
    """Normalise NFKD → ASCII → lowercase."""
    normalized = unicodedata.normalize("NFKD", s)
    return normalized.encode("ascii", "ignore").decode("ascii").lower()


def strip_html(html_text):
    """
    Supprime les balises HTML et normalise les espaces.

    Args:
        html_text : chaîne de caractères pouvant contenir du HTML

    Returns:
        str : texte brut sans balises, espaces normalisés
    """
    if not html_text:
        return ""
    text = re.sub(r"<[^>]+>", " ", html_text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def slugify(text):
    """
    Convertit un texte en handle Shopify valide (slug URL).

    Traitement :
      1. Normalisation NFKD → ASCII (suppression des accents)
      2. Minuscules
      3. Garde uniquement [a-z0-9 -]
      4. Espaces convertis en tirets
      5. Dédoublonnage des tirets consécutifs
      6. Troncature à 255 chars maximum
      7. Strip des tirets aux extrémités

    Args:
        text : texte source à slugifier

    Returns:
        str : handle Shopify valide
    """
    if not text:
        return ""
    normalized = unicodedata.normalize("NFKD", text)
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    lower      = ascii_text.lower()
    cleaned    = re.sub(r"[^a-z0-9\s-]", "", lower)
    with_hyphens = re.sub(r"\s+", "-", cleaned)
    deduplicated = re.sub(r"-{2,}", "-", with_hyphens)
    return deduplicated[:255].strip("-")


def _simple_hash(s):
    """
    Hash simple entier positif — porte l'algo JS (hash << 5) - hash + charCode.

    Args:
        s : chaîne de caractères

    Returns:
        int : valeur absolue du hash
    """
    h = 0
    for ch in s:
        h = ((h << 5) - h + ord(ch)) & 0xFFFFFFFF
    # Convertir en entier signé 32 bits puis prendre la valeur absolue
    if h >= 0x80000000:
        h -= 0x100000000
    return abs(h)


def extract_product_identity(title):
    """
    Normalise un titre produit en supprimant les mots couleur.

    Args:
        title : titre du produit

    Returns:
        str : identité normalisée sans couleurs
    """
    normalized = _normalize_str(title)
    for color in COLOR_WORDS:
        normalized = re.sub(r'\b' + re.escape(color) + r'\b', '', normalized)
    normalized = re.sub(r'\s+', ' ', normalized)
    normalized = re.sub(r'-+', '-', normalized)
    return normalized.strip()


def extract_handle_identity(handle):
    """
    Normalise un handle Shopify en supprimant les segments couleur.

    Args:
        handle : handle Shopify (slug)

    Returns:
        str : handle normalisé sans segments couleur
    """
    normalized = _normalize_str(handle)
    segments   = normalized.split('-')
    filtered   = [seg for seg in segments if seg not in COLOR_WORDS]
    joined     = '-'.join(filtered)
    joined     = re.sub(r'-{2,}', '-', joined)
    return joined.strip('-')


def levenshtein_distance(a, b):
    """
    Calcule la distance de Levenshtein entre deux chaînes.

    Args:
        a : première chaîne
        b : deuxième chaîne

    Returns:
        int : distance d'édition
    """
    m, n = len(a), len(b)
    matrix = [[0] * (n + 1) for _ in range(m + 1)]
    for i in range(m + 1):
        matrix[i][0] = i
    for j in range(n + 1):
        matrix[0][j] = j
    for i in range(1, m + 1):
        for j in range(1, n + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )
    return matrix[m][n]


def similarity(a, b):
    """
    Calcule la similarité entre deux chaînes (0.0 à 1.0).

    Args:
        a : première chaîne
        b : deuxième chaîne

    Returns:
        float : 1 - levenshtein(a, b) / max(len(a), len(b))
    """
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 1.0
    return 1.0 - levenshtein_distance(a, b) / max_len


def clean_differentiator(niche_keyword, differentiator):
    """
    Filtre les mots de la niche et les size adjectives du differentiator.

    Porte exactement la logique JS : itère mot par mot sur le differentiator,
    saute les séquences qui matchent la niche complète, saute les mots isolés
    de la niche, saute les SIZE_ADJECTIVES.

    Args:
        niche_keyword  : mot-clé de la niche
        differentiator : attributs différenciants bruts

    Returns:
        str : mots filtrés joints par espace
    """
    niche_words = [_normalize_str(w) for w in niche_keyword.split()]
    diff_words  = differentiator.split()
    result      = []
    i           = 0

    while i < len(diff_words):
        word_norm = _normalize_str(diff_words[i])

        # Vérifie si la séquence à la position i matche la niche complète
        if (i + len(niche_words) <= len(diff_words) and
                all(_normalize_str(diff_words[i + j]) == niche_words[j] for j in range(len(niche_words)))):
            i += len(niche_words)
            continue

        # Saute les mots isolés de la niche
        if word_norm in niche_words:
            i += 1
            continue

        # Saute les SIZE_ADJECTIVES
        if word_norm in SIZE_ADJECTIVES:
            i += 1
            continue

        result.append(diff_words[i])
        i += 1

    return ' '.join(result)


def build_h1(branding_name, niche_keyword, differentiator, branding_position="start"):
    """
    Construit le H1 algorithmiquement.

    Si branding_name est vide (mode characteristics) :
        "{niche_keyword} {cleaned}"
    Sinon, selon branding_position :
        "start" : "{branding_name} – {niche_keyword} {cleaned}"
        "end"   : "{niche_keyword} {cleaned} – {branding_name}"

    Args:
        branding_name      : nom branding (vide si mode characteristics)
        niche_keyword      : mot-clé de la niche
        differentiator     : attributs différenciants bruts
        branding_position  : "start" ou "end"

    Returns:
        str : H1 construit
    """
    cleaned = clean_differentiator(niche_keyword, differentiator)

    if not branding_name:
        parts = [niche_keyword]
        if cleaned:
            parts.append(cleaned)
        return ' '.join(parts).strip()

    if branding_position == "end":
        parts = [niche_keyword]
        if cleaned:
            parts.append(cleaned)
        parts += ['–', branding_name]
    else:  # "start" (défaut)
        parts = [branding_name, '–', niche_keyword]
        if cleaned:
            parts.append(cleaned)

    return ' '.join(parts).strip()


def build_meta_title(niche_keyword, differentiator, vendor):
    """
    Construit le meta title algorithmiquement.

    Sépare le differentiator en bloc1 (termes fonctionnels) et bloc2 (style/couleur).
    Format : "{niche_keyword} {bloc1} | {bloc2} | {vendor}" ou
             "{niche_keyword} {bloc1} | {vendor}"
    Tronqué à 150 chars au dernier mot complet.

    Args:
        niche_keyword  : mot-clé de la niche
        differentiator : attributs différenciants bruts
        vendor         : nom de la boutique

    Returns:
        str : meta title construit
    """
    cleaned = clean_differentiator(niche_keyword, differentiator)

    if not cleaned:
        return f"{niche_keyword} | {vendor}"

    bloc1 = []
    bloc2 = []

    for word in cleaned.split():
        word_norm = _normalize_str(word)
        if word_norm in STYLE_COULEUR:
            bloc2.append(word)
        else:
            bloc1.append(word)

    if bloc2:
        meta = f"{niche_keyword} {' '.join(bloc1)} | {' '.join(bloc2)} | {vendor}"
    else:
        meta = f"{niche_keyword} {' '.join(bloc1)} | {vendor}"

    if len(meta) > 150:
        truncated = meta[:150]
        last_space = truncated.rfind(' ')
        if last_space > 0:
            meta = truncated[:last_space]
        else:
            meta = truncated

    return meta


def pick_theme_branding(title, handle, pool, state):
    """
    Sélectionne un nom branding depuis un pool en réutilisant les noms pour les variantes.

    state est un dict mutable : {"used_names": set(), "identity_map": {}, "handle_identity_map": {}}.
    Porte exactement la logique JS de generateBrandingName.

    Args:
        title  : titre du produit
        handle : handle Shopify du produit
        pool   : liste de noms branding disponibles
        state  : dict d'état partagé entre tous les produits

    Returns:
        str : nom branding sélectionné
    """
    title_identity = extract_product_identity(title)
    handle_id      = extract_handle_identity(handle)

    # Check identity_map (exact)
    if title_identity in state["identity_map"]:
        return state["identity_map"][title_identity]

    # Check handle_identity_map (exact)
    if handle_id in state["handle_identity_map"]:
        name = state["handle_identity_map"][handle_id]
        state["identity_map"][title_identity] = name
        return name

    # Check par similarité handles
    for existing_handle_id, existing_name in state["handle_identity_map"].items():
        if similarity(handle_id, existing_handle_id) >= SIMILARITY_THRESHOLD:
            state["identity_map"][title_identity]      = existing_name
            state["handle_identity_map"][handle_id]    = existing_name
            return existing_name

    # Nouveau nom depuis le pool
    available = [n for n in pool if n not in state["used_names"]]

    if available:
        idx  = _simple_hash(title_identity) % len(available)
        name = available[idx]
    else:
        base = pool[_simple_hash(title_identity) % len(pool)]
        name = base
        suffix = 2
        while name in state["used_names"]:
            name = f"{base}{suffix}"
            suffix += 1

    state["used_names"].add(name)
    state["identity_map"][title_identity]   = name
    state["handle_identity_map"][handle_id] = name

    return name


def generate_ai_branding_name(product_keyword, niche_keyword, supplier_description, title, handle, state, openai_client, cost_tracker, max_retries=3):
    """
    Génère ou réutilise un nom branding IA pour un produit.

    Vérifie d'abord si une variante couleur existante peut être réutilisée.
    Sinon appelle OpenAI avec build_boost_ai_branding_prompt.

    Args:
        product_keyword      : mot-clé principal du produit
        niche_keyword        : mot-clé de niche
        supplier_description : description fournisseur (peut être vide)
        title                : titre du produit (pour extract_product_identity)
        handle               : handle Shopify (pour extract_handle_identity)
        state                : dict d'état {"used_names": set(), "identity_map": {}, "handle_identity_map": {}}
        openai_client        : instance openai.OpenAI
        cost_tracker         : instance CostTracker
        max_retries          : nombre max de tentatives

    Returns:
        str : nom branding généré ou réutilisé

    Raises:
        Exception : si toutes les tentatives échouent
    """
    title_identity = extract_product_identity(title)
    handle_id      = extract_handle_identity(handle)

    # Check variante couleur existante
    if title_identity in state["identity_map"]:
        return state["identity_map"][title_identity]

    if handle_id in state["handle_identity_map"]:
        name = state["handle_identity_map"][handle_id]
        state["identity_map"][title_identity] = name
        return name

    for existing_handle_id, existing_name in state["handle_identity_map"].items():
        if similarity(handle_id, existing_handle_id) >= SIMILARITY_THRESHOLD:
            state["identity_map"][title_identity]   = existing_name
            state["handle_identity_map"][handle_id] = existing_name
            return existing_name

    # Génération via OpenAI
    prompt = build_boost_ai_branding_prompt(product_keyword, niche_keyword, supplier_description)

    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=OPENAI_TEMPERATURE,
            )
            cost_tracker.add(response.usage)
            name = response.choices[0].message.content.strip()

            # Vérifier unicité, retry si doublon
            if name in state["used_names"] and attempt < max_retries - 1:
                log(f"Branding name doublon — {name!r} déjà utilisé, retry ({attempt+1}/{max_retries})", "warning")
                time.sleep(2 ** attempt)
                continue

            log(
                f"Branding name IA OK — produit: {product_keyword!r} | "
                f"nom: {name!r} | "
                f"tokens: {response.usage.prompt_tokens}in/{response.usage.completion_tokens}out | "
                f"coût session: ${cost_tracker.cost_usd:.4f}"
            )

            state["used_names"].add(name)
            state["identity_map"][title_identity]   = name
            state["handle_identity_map"][handle_id] = name

            return name

        except Exception as e:
            err = str(e)
            log(
                f"Erreur génération branding name IA — {product_keyword!r} | {err} (tentative {attempt+1}/{max_retries})",
                "error", also_print=True
            )
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise Exception(f"Échec génération branding name IA après {max_retries} tentatives : {err}")

    raise Exception("Impossible de générer le branding name IA après plusieurs tentatives.")


def generate_differentiator(product_keyword, niche_keyword, supplier_description, seo_keywords, openai_client, cost_tracker, max_retries=3):
    """
    Génère les attributs différenciants d'un produit via OpenAI (texte brut, 1 ligne).

    Args:
        product_keyword      : mot-clé principal du produit
        niche_keyword        : mot-clé de niche
        supplier_description : description fournisseur (peut être vide)
        seo_keywords         : bloc keywords SEO formaté (peut être vide)
        openai_client        : instance openai.OpenAI
        cost_tracker         : instance CostTracker
        max_retries          : nombre max de tentatives

    Returns:
        str : attributs différenciants (une ligne)

    Raises:
        Exception : si toutes les tentatives échouent
    """
    prompt = build_boost_differentiator_prompt(product_keyword, niche_keyword, supplier_description, seo_keywords)

    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=OPENAI_TEMPERATURE_LOW,
            )
            cost_tracker.add(response.usage)
            raw = response.choices[0].message.content.strip()
            # Supprime tous les guillemets entourants (GPT entoure parfois le résultat de quotes)
            differentiator = re.sub(r'^["""\'«»]+|["""\'«»]+$', '', raw).strip()

            log(
                f"Differentiator OK — produit: {product_keyword!r} | "
                f"diff: {differentiator!r} | "
                f"tokens: {response.usage.prompt_tokens}in/{response.usage.completion_tokens}out | "
                f"coût session: ${cost_tracker.cost_usd:.4f}"
            )
            return differentiator

        except Exception as e:
            err = str(e)
            log(
                f"Erreur génération differentiator — {product_keyword!r} | {err} (tentative {attempt+1}/{max_retries})",
                "error", also_print=True
            )
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise Exception(f"Échec génération differentiator après {max_retries} tentatives : {err}")

    raise Exception("Impossible de générer le differentiator après plusieurs tentatives.")


def generate_description(product_keyword, niche_keyword, supplier_description, branding_name, word_count, openai_client, cost_tracker, seo_keywords="", collections=None, max_retries=3):
    """
    Génère la description HTML SEO d'un produit via OpenAI.

    Args:
        product_keyword      : mot-clé principal (H1 avec branding)
        niche_keyword        : mot-clé de niche
        supplier_description : description fournisseur (peut être vide)
        branding_name        : nom de modèle branding (peut être vide)
        word_count           : nombre minimum de mots
        openai_client        : instance openai.OpenAI
        cost_tracker         : instance CostTracker
        seo_keywords         : bloc keywords SEO formaté (peut être vide)
        collections          : liste de dicts {name, url} pour le maillage interne
        max_retries          : nombre max de tentatives

    Returns:
        str : description HTML générée

    Raises:
        Exception : si toutes les tentatives échouent
    """
    prompt = build_boost_description_prompt(product_keyword, niche_keyword, supplier_description, branding_name, word_count, seo_keywords, collections)

    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=OPENAI_TEMPERATURE_LOW,
            )
            cost_tracker.add(response.usage)
            raw_desc    = response.choices[0].message.content.strip()
            # Supprime les balises markdown ```html ... ``` que GPT ajoute parfois
            description = re.sub(r'^```[a-zA-Z]*\s*', '', raw_desc)
            description = re.sub(r'\s*```$', '', description).strip()

            log(
                f"Description HTML OK — produit: {product_keyword!r} | "
                f"tokens: {response.usage.prompt_tokens}in/{response.usage.completion_tokens}out | "
                f"coût session: ${cost_tracker.cost_usd:.4f}"
            )
            return description

        except Exception as e:
            err = str(e)
            log(
                f"Erreur génération description — {product_keyword!r} | {err} (tentative {attempt+1}/{max_retries})",
                "error", also_print=True
            )
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise Exception(f"Échec génération description après {max_retries} tentatives : {err}")

    raise Exception("Impossible de générer la description après plusieurs tentatives.")


def generate_meta_description(product_keyword, niche_keyword, supplier_description, seo_keywords, openai_client, cost_tracker, max_retries=3):
    """
    Génère la meta description via OpenAI (format JSON).

    Args:
        product_keyword      : mot-clé principal du produit
        niche_keyword        : mot-clé de niche
        supplier_description : description fournisseur (peut être vide)
        seo_keywords         : termes SEO supplémentaires (peut être vide)
        openai_client        : instance openai.OpenAI
        cost_tracker         : instance CostTracker
        max_retries          : nombre max de tentatives

    Returns:
        str : meta description générée

    Raises:
        Exception : si toutes les tentatives échouent
    """
    prompt = build_boost_meta_prompt(product_keyword, niche_keyword, supplier_description, seo_keywords)

    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model=OPENAI_MODEL,
                messages=[{"role": "user", "content": prompt}],
                temperature=OPENAI_TEMPERATURE,
                response_format={"type": "json_object"},
            )
            cost_tracker.add(response.usage)

            content     = response.choices[0].message.content
            data        = json.loads(content)
            description = data["description"]

            log(
                f"Meta description OK — produit: {product_keyword!r} | "
                f"tokens: {response.usage.prompt_tokens}in/{response.usage.completion_tokens}out | "
                f"coût session: ${cost_tracker.cost_usd:.4f}"
            )
            return description

        except Exception as e:
            err = str(e)
            log(
                f"Erreur génération meta description — {product_keyword!r} | {err} (tentative {attempt+1}/{max_retries})",
                "error", also_print=True
            )
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                raise Exception(f"Échec génération meta description après {max_retries} tentatives : {err}")

    raise Exception("Impossible de générer la meta description après plusieurs tentatives.")


def generate_handle(h1_title):
    """
    Génère un handle Shopify à partir du H1 via slugify (pas d'appel OpenAI).

    Args:
        h1_title : titre H1 du produit

    Returns:
        str : handle Shopify valide (max 255 chars)
    """
    return slugify(h1_title)
