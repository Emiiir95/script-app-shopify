#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
utils/taxonomy.py — Taxonomie produit Shopify (publique, en français).

Sert au bouton « Récupérer les catégories » : pour chaque niche d'une boutique,
trouve automatiquement la catégorie Shopify la plus proche (nom FR + GID).

Source : la taxonomie publique de Shopify, publiée en français, avec les mêmes
GID que l'API Admin (les GID de catégorie sont universels — indépendants de la
boutique). On la télécharge une fois et on la met en cache localement.

Choix de la catégorie la plus proche, en 2 temps :
  1. Pré-filtrage LEXICAL : score par chevauchement de mots (feuille + chemin),
     singularisation simple, sans accent/casse → garde les meilleurs candidats.
  2. Choix SÉMANTIQUE (IA, optionnel) : si une clé OpenAI est fournie, GPT choisit
     le meilleur candidat de la liste (gère les synonymes : « porte/arbre » →
     « support », etc.). Sinon, on garde le 1er candidat lexical (repli).

Fonctions publiques :
  - download_taxonomy(force=False)         : télécharge/rafraîchit le cache, retourne le chemin
  - parse_taxonomy_text(text)              : parse le fichier en entrées {gid, name, full_name, ...}
  - load_taxonomy()                        : charge (et télécharge si besoin) les entrées
  - rank_candidates(niche, entries, top)   : meilleurs candidats lexicaux [(score, entry)]
  - choose_category_ai(niche, cands, client): GID choisi par GPT parmi les candidats
  - niche_match_keywords(niche)            : mots-clés de match d'une niche (pour category_rules)
  - suggest_categories(niches, ...)        : règles prêtes pour category_rules
"""

import json
import os
import re
import time
import unicodedata
import urllib.request

from utils.logger import log

TAXONOMY_URL = "https://raw.githubusercontent.com/Shopify/product-taxonomy/main/dist/fr/categories.txt"

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_CACHE_DIR    = os.path.join(_PROJECT_ROOT, "cache")
_CACHE_FILE   = os.path.join(_CACHE_DIR, "shopify_taxonomy_fr.txt")
_CACHE_TTL    = 30 * 24 * 3600   # 30 jours

# Mots vides ignorés (matching et scoring)
_STOPWORDS = {
    "a", "au", "aux", "avec", "d", "de", "des", "du", "en", "et", "l", "la",
    "le", "les", "pour", "sur", "un", "une",
}


# ── Normalisation texte ─────────────────────────────────────────────────────────

def _norm(text):
    """Minuscules, sans accent, ponctuation → espaces."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def _singularize(word):
    """Singularisation naïve FR : retire un 's' final (boîtes→boite, montres→montre)."""
    return word[:-1] if len(word) > 3 and word.endswith("s") else word


def _tokens(text):
    """Mots significatifs, normalisés + singularisés, sans mots vides."""
    return [
        _singularize(w) for w in _norm(text).split()
        if w not in _STOPWORDS and len(w) > 1
    ]


def niche_match_keywords(niche):
    """
    Mots-clés de match d'une niche pour category_rules (un mot-clé multi-mots).

    Ex : "Boîte à Montre" → ["boite montre"] (exige boite ET montre présents).
    """
    words = _tokens(niche)
    return [" ".join(words)] if words else []


# ── Téléchargement / cache / parsing ────────────────────────────────────────────

def download_taxonomy(force=False, url=TAXONOMY_URL, cache_file=_CACHE_FILE):
    """
    Télécharge la taxonomie FR et la met en cache. Retourne le chemin du cache.

    Ne re-télécharge pas si le cache existe et a moins de _CACHE_TTL (sauf force=True).
    Lève ValueError si le téléchargement échoue ET qu'aucun cache n'est disponible.
    """
    fresh = (
        os.path.isfile(cache_file)
        and (time.time() - os.path.getmtime(cache_file)) < _CACHE_TTL
    )
    if fresh and not force:
        return cache_file

    try:
        req = urllib.request.Request(url, headers={"User-Agent": "shopify-automation/1.0"})
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = resp.read().decode("utf-8")
        os.makedirs(os.path.dirname(cache_file), exist_ok=True)
        with open(cache_file, "w", encoding="utf-8") as f:
            f.write(data)
        log(f"Taxonomie Shopify téléchargée : {cache_file}")
        return cache_file
    except Exception as e:
        if os.path.isfile(cache_file):
            log(f"Téléchargement taxonomie échoué ({e}) — cache existant réutilisé.", "warning")
            return cache_file
        raise ValueError(f"Impossible de télécharger la taxonomie Shopify : {e}")


def parse_taxonomy_text(text):
    """
    Parse le fichier categories.txt en liste d'entrées.

    Chaque ligne : "gid://shopify/TaxonomyCategory/xxx    : A > B > Feuille".

    Returns:
        list de dicts { gid, name, full_name, name_words (set), path_words (set) }.
    """
    entries = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or " : " not in line:
            continue
        gid_part, _, full_name = line.partition(" : ")
        gid       = gid_part.strip()
        full_name = full_name.strip()
        if not gid.startswith("gid://shopify/TaxonomyCategory/"):
            continue
        name = full_name.split(">")[-1].strip()
        entries.append({
            "gid":        gid,
            "name":       name,
            "full_name":  full_name,
            "name_words": set(_tokens(name)),
            "path_words": set(_tokens(full_name)),
        })
    return entries


def load_taxonomy(force=False):
    """Charge les entrées de la taxonomie (télécharge/rafraîchit le cache si besoin)."""
    path = download_taxonomy(force=force)
    with open(path, encoding="utf-8") as f:
        return parse_taxonomy_text(f.read())


# ── Scoring lexical ─────────────────────────────────────────────────────────────

def _score(niche_words, entry):
    """
    Score de proximité entre une niche et une catégorie.

    + fort si les mots de la niche sont dans le NOM de la feuille ; + faible s'ils
    sont ailleurs dans le chemin ; bonus si la niche est entièrement incluse ;
    petite pénalité pour les mots superflus de la feuille.
    """
    leaf = entry["name_words"]
    inter_leaf = niche_words & leaf
    score = 3.0 * len(inter_leaf) + 1.0 * len(niche_words & entry["path_words"])
    if niche_words and niche_words <= leaf:
        score += 3.0
    score -= 0.5 * len(leaf - niche_words)
    return score


def rank_candidates(niche, entries, top=25):
    """
    Retourne les meilleurs candidats lexicaux pour une niche : liste [(score, entry)]
    triée par score décroissant, limitée à `top`, uniquement score > 0.
    """
    niche_words = set(_tokens(niche))
    scored = [(_score(niche_words, e), e) for e in entries]
    scored = [(s, e) for s, e in scored if s > 0]
    scored.sort(key=lambda t: t[0], reverse=True)
    return scored[:top]


def gather_candidates(niche, entries, per_word=40, overall=15):
    """
    Rassemble un jeu de candidats DIVERSIFIÉ pour l'IA.

    Problème du seul top-N global : sur « Porte Bijoux », les dizaines de catégories
    « porte-* » noient la bonne (« Support pour bijoux ») — et lexicalement toutes les
    catégories « … bijoux » sont à égalité. On inclut donc, POUR CHAQUE mot de la niche,
    TOUTES les catégories dont la FEUILLE contient ce mot (plafonné, triées par proximité
    globale) — ainsi la dimension « porte » ET la dimension « bijoux » sont couvertes en
    entier — puis on ajoute le top-N global. Union dédoublonnée par GID. L'IA tranche
    ensuite sémantiquement (porte/arbre → support…).

    Returns:
        list d'entrées (dicts) — les candidats à soumettre à l'IA.
    """
    words  = set(_tokens(niche))
    picked = {}

    for w in words:
        leaf_matches = [e for e in entries if w in e["name_words"]]
        leaf_matches.sort(key=lambda e: _score(words, e), reverse=True)
        for e in leaf_matches[:per_word]:
            picked[e["gid"]] = e

    for _, e in rank_candidates(niche, entries, top=overall):
        picked[e["gid"]] = e

    return list(picked.values())


# ── Choix sémantique (IA) ───────────────────────────────────────────────────────

def choose_category_ai(niche, candidates, openai_client, model="gpt-4o-mini"):
    """
    Demande à GPT de choisir la catégorie la plus proche parmi `candidates`.

    Args:
        niche          : nom de la niche (str)
        candidates     : liste d'entrées {gid, full_name} (les meilleurs candidats lexicaux)
        openai_client  : client OpenAI déjà instancié

    Returns:
        str GID choisi (présent dans candidates) ou None si échec / choix invalide.
    """
    if not candidates:
        return None
    # Accepte le GID complet OU l'id court (le modèle renvoie parfois "hb-2-3-2"
    # au lieu de "gid://shopify/TaxonomyCategory/hb-2-3-2").
    by_short = {c["gid"].rsplit("/", 1)[-1]: c["gid"] for c in candidates}
    listing = "\n".join(f'{c["gid"]} = {c["full_name"]}' for c in candidates)
    prompt = (
        "Tu ranges un produit dans la taxonomie Shopify.\n"
        f'Niche du produit : "{niche}".\n\n'
        "Choisis LA catégorie la plus proche parmi cette liste (et uniquement celle-ci) :\n"
        f"{listing}\n\n"
        'Réponds en JSON strict : {"gid": "<le gid exact choisi>"}.'
    )
    try:
        resp = openai_client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": prompt}],
            response_format={"type": "json_object"},
            temperature=0,
        )
        gid = (json.loads(resp.choices[0].message.content) or {}).get("gid", "").strip()
        return by_short.get(gid.rsplit("/", 1)[-1])
    except Exception as e:
        log(f"Choix IA catégorie échoué pour {niche!r} : {e}", "warning")
        return None


# ── Suggestion complète ─────────────────────────────────────────────────────────

def suggest_categories(niches, openai_key=None, entries=None, top=25, _client=None):
    """
    Pour chaque niche, construit une règle category_rules avec la catégorie la plus proche.

    1. Pré-filtre lexical (rank_candidates).
    2. Si openai_key/_client fourni : GPT choisit parmi les candidats (choose_category_ai).
       Sinon : 1er candidat lexical (repli).

    Args:
        niches     : liste de noms de niches (str)
        openai_key : clé OpenAI (str) ou None → mode lexical uniquement
        entries    : entrées taxonomie déjà chargées (sinon load_taxonomy())
        _client    : client OpenAI injecté (tests) — prioritaire sur openai_key

    Returns:
        list de dicts { match, name, search, gid, fullName, found, via, niche } — une par niche.
        `via` = "ai" | "lexical" | "none". `found` = True si une catégorie a été retenue.
    """
    if entries is None:
        entries = load_taxonomy()

    client = _client
    if client is None and openai_key:
        try:
            from openai import OpenAI
            client = OpenAI(api_key=openai_key)
        except Exception as e:
            log(f"Client OpenAI indisponible ({e}) — matching lexical uniquement.", "warning")
            client = None

    rules = []
    for niche in niches:
        niche = (niche or "").strip()
        if not niche:
            continue
        match       = niche_match_keywords(niche)
        niche_words = set(_tokens(niche))
        candidates  = gather_candidates(niche, entries)
        chosen      = None
        via         = "none"

        if client and candidates:
            gid = choose_category_ai(niche, candidates, client)
            if gid:
                chosen = next((e for e in candidates if e["gid"] == gid), None)
                via = "ai"
        if chosen is None and candidates:
            # Repli lexical : meilleur score global parmi les candidats
            chosen = max(candidates, key=lambda e: _score(niche_words, e))
            via = "lexical"

        if chosen:
            rules.append({
                "match":    match,
                "name":     chosen["name"],
                "search":   "",
                "gid":      chosen["gid"],
                "fullName": chosen["full_name"],
                "found":    True,
                "via":      via,
                "niche":    niche,
            })
        else:
            rules.append({
                "match":    match,
                "name":     niche,
                "search":   "",
                "gid":      None,
                "fullName": "",
                "found":    False,
                "via":      "none",
                "niche":    niche,
            })

    # Le plus spécifique d'abord (plus de mots-clés = priorité) — sécurité d'ordre
    rules.sort(key=lambda r: -len((r["match"][0] if r["match"] else "").split()))
    return rules
