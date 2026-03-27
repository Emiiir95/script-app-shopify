#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompts.py — Prompts OpenAI pour la feature Fiche Produit.

Port exact des fonctions JS de prompts-boost.js :
  - build_phrase_prompt          → buildBoostPhrasePrompt
  - build_shorten_phrase_prompt  → buildBoostShortenPhrasePrompt
  - build_benefices_prompt       → buildBoostBeneficesPrompt
  - build_specs_prompt           → buildBoostSpecsPrompt
  - build_titres_prompt          → buildBoostTitresPrompt
  - build_descriptions_prompt    → buildBoostDescriptionsPrompt

La constante INTERDICTIONS est partagée par tous les prompts.
"""

INTERDICTIONS = """❌ Pays d'origine, marques, fabricants
❌ garantie, garanti, offre, promo, gratuit, livraison"""


def build_phrase_prompt(product_keyword, niche_keyword, reassurance_points, supplier_description):
    """
    Prompt pour la phrase d'accroche commerciale (max 70 caractères).
    Port exact de buildBoostPhrasePrompt (prompts-boost.js).
    """
    reassurance = reassurance_points.strip() if reassurance_points and reassurance_points.strip() else ""
    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""CONTEXTE FOURNISSEUR :
\"\"\"
{supplier_description.strip()}
\"\"\"
"""

    return f"""Copywriter e-commerce premium. Génère UNE phrase d'accroche pour "{product_keyword}".

{supplier_block}
POINTS DE RÉASSURANCE :
{reassurance}

STYLE : Phrase MARKETING premium, ton élégant, "pitch de marque" (pas descriptif/technique).

CONTRAINTES :
- MAX 70 caractères (espaces inclus), texte brut, UNE phrase
- NE PAS commencer par "{niche_keyword}"

❌ Pas d'infos techniques inventées, pas de caractéristiques listées
❌ Pas de "idéal pour", "parfait pour", "conçu pour"
{INTERDICTIONS}

Retourne UNIQUEMENT la phrase (max 70 chars).
"""


def build_shorten_phrase_prompt(phrase):
    """
    Prompt pour raccourcir une phrase trop longue à 70 caractères max.
    Port exact de buildBoostShortenPhrasePrompt (prompts-boost.js).
    """
    return f"""Raccourcis cette phrase à 70 caractères maximum.
Garde le sens, orientée conversion produit. Pas de phrase vague.

Phrase : "{phrase}"

Retourne UNIQUEMENT la phrase raccourcie, sans guillemets.
"""


def build_benefices_prompt(product_keyword, niche_keyword, reassurance_points, supplier_description):
    """
    Prompt pour les 3 bénéfices courts orientés conversion.
    Port exact de buildBoostBeneficesPrompt (prompts-boost.js).
    """
    reassurance = reassurance_points.strip() if reassurance_points and reassurance_points.strip() else ""
    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""CONTEXTE FOURNISSEUR :
\"\"\"
{supplier_description.strip()}
\"\"\"

Base chaque bénéfice sur les VRAIES caractéristiques.
"""

    return f"""Génère EXACTEMENT 3 bénéfices courts pour "{product_keyword}".
Chaque bénéfice doit convertir : le client lit et se dit "c'est ce qu'il me faut".

{supplier_block}
RÉASSURANCE (inspire-toi des plus pertinents) :
{reassurance}

RÈGLES :
- 2 à 5 mots max par bénéfice, UNIVERSEL (pas de limites restrictives)
- Chaque mot apporte de la valeur, orienté BÉNÉFICE ÉMOTIONNEL
- EXACTEMENT 3 lignes, max 40 chars chacun, texte brut

❌ Pas de HTML, pas de "Titre : description", pas de "...", pas de guillemets
❌ Pas de chiffres limitants, pas de précisions évidentes, pas de mots creux
{INTERDICTIONS}

LOGIQUE : Lis réassurance → croise avec caractéristiques → formule en 2-5 mots percutants.

Retourne UNIQUEMENT 3 lignes, texte brut.
"""


def build_specs_prompt(product_keyword, supplier_description):
    """
    Prompt pour les caractéristiques techniques HTML.
    Port exact de buildBoostSpecsPrompt (prompts-boost.js).
    """
    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""DESCRIPTION FOURNISSEUR :
\"\"\"
{supplier_description.strip()}
\"\"\"

Extrait UNIQUEMENT les données techniques RÉELLES.
"""

    return f"""Générateur de caractéristiques techniques e-commerce. Réponds UNIQUEMENT en HTML.

PRODUIT : {product_keyword}

{supplier_block}
RÈGLES :
- 8-12 caractéristiques : <li>Libellé : Description technique</li>
- UNIQUEMENT infos présentes dans la description, N'INVENTE RIEN
- Unités normalisées : cm, kg, W, etc.

{INTERDICTIONS}

FORMAT : <ul><li>Libellé : Description</li></ul>

Retourne UNIQUEMENT <ul>...</ul>.
"""


def build_titres_prompt(product_keyword, niche_keyword, reassurance_points, supplier_description):
    """
    Prompt pour les 2 titres de sections.
    Port exact de buildBoostTitresPrompt (prompts-boost.js).
    """
    reassurance = reassurance_points.strip() if reassurance_points and reassurance_points.strip() else ""
    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""CONTEXTE FOURNISSEUR :
\"\"\"
{supplier_description.strip()}
\"\"\"
"""

    return f"""Génère EXACTEMENT 2 titres de sections pour "{product_keyword}".

{supplier_block}
RÉASSURANCE :
{reassurance}

RÈGLES :
- Texte brut, pas de HTML/guillemets/numérotation
- 2 titres TRÈS DIFFÉRENTS l'un de l'autre (angles différents)
- Max 10 mots chacun, orienté bénéfice client
- UNE ligne par titre, séparés par un saut de ligne

FORMAT ATTENDU (2 lignes distinctes, rien d'autre) :
Un confort incomparable pour votre chat
Un design élégant qui s'intègre partout

{INTERDICTIONS}

Retourne UNIQUEMENT ces 2 lignes, sans introduction ni commentaire.
"""


def build_descriptions_prompt(product_keyword, reassurance_points, titres, supplier_description):
    """
    Prompt pour les 2 descriptions HTML avec icônes (feature sections).
    Port exact de buildBoostDescriptionsPrompt (prompts-boost.js).

    Args:
        titres : liste [titre1, titre2]
    """
    reassurance = reassurance_points.strip() if reassurance_points and reassurance_points.strip() else ""
    titre1 = titres[0] if len(titres) > 0 else ""
    titre2 = titres[1] if len(titres) > 1 else ""
    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""CONTEXTE FOURNISSEUR :
\"\"\"
{supplier_description.strip()}
\"\"\"
"""

    return f"""Génère EXACTEMENT 2 descriptions HTML pour "{product_keyword}".

{supplier_block}
RÉASSURANCE :
{reassurance}

TITRE 1 : {titre1}
TITRE 2 : {titre2}

FORMAT par description :
<style>.feature-item-xyz123{{display:flex;align-items:center;margin-bottom:15px}}.feature-item-xyz123:last-child{{margin-bottom:0}}.check-icon-xyz123{{width:24px;height:24px;margin-right:10px}}.feature-text-xyz123{{font-size:14px;color:#333}}</style>
<p style='color:black;margin-top:-5px'>[Phrase rassurante basée sur le titre]</p>
<div class="feature-item-xyz123"><img src="https://www.svgrepo.com/show/507980/check-badge.svg" alt="Check Icon" class="check-icon-xyz123"><div class="feature-text-xyz123">[Bénéfice]</div></div>
(3 feature-items par description)

RÈGLES :
- 2 descriptions COMPLÈTES ET DIFFÉRENTES, séparées par "---SEPARATOR---"
- Chaque : style CSS + 1 paragraphe + 3 features

{INTERDICTIONS}

FORMAT DE SORTIE :
[Description 1]
---SEPARATOR---
[Description 2]

HTML pur uniquement.
"""
