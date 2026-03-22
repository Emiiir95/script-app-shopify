#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompts.py — Prompts OpenAI pour la feature Collections.

Fonctions publiques :
  - build_collection_description_prompt : description 1000+ mots, 8 H2, bullets points
  - build_collection_meta_title_prompt  : meta title SEO 60-70 chars
  - build_collection_meta_desc_prompt   : meta description SEO ~155 chars
"""

INTERDICTIONS = """❌ Pays d'origine, marques, fabricants
❌ garantie, garanti, offre, promo, gratuit, livraison"""


def build_collection_description_prompt(collection_name, niche_keyword, tags, seo_keywords=""):
    """
    Construit le prompt pour générer la description HTML d'une page collection.
    Structure en 8 H2 : angles progressifs (sensoriel → multifonction → technologie →
    feature → usage → expérience → comparaison → conclusion "Pourquoi choisir").

    Args:
        collection_name : nom de la collection (ex: "Arbre à Chat XXL")
        niche_keyword   : mot-clé de niche (ex: "Arbre à Chat")
        tags            : liste de tags de la collection (ex: ["arbre a chat xxl"])
        seo_keywords    : bloc keywords CSV formaté (peut être vide)

    Returns:
        str : prompt complet pour OpenAI
    """
    tags_str = ", ".join(tags)

    seo_block = ""
    if seo_keywords and seo_keywords.strip():
        seo_block = f"""
MOTS-CLÉS SEO À INTÉGRER :
{seo_keywords.strip()}

→ Intègre naturellement ces termes dans les H2 et les paragraphes.
"""

    return f"""RÔLE : Rédacteur SEO e-commerce expert. Réponds UNIQUEMENT en HTML pur.

⚠️ HTML uniquement : <strong> pour le gras (JAMAIS **), <h2> pour titres (JAMAIS #), JAMAIS de <h1>

COLLECTION : "{collection_name}"
NICHE : "{niche_keyword}"
MOTS-CLÉS CIBLÉS : "{tags_str}"
{seo_block}
OBJECTIF : Rédiger une fiche collection qui répond aux questions et besoins du client, l'aide à choisir, et le rassure sur sa décision d'achat. Ton factuel, bienveillant, centré sur le client.

INTERDICTIONS ABSOLUES :
{INTERDICTIONS}
❌ Mention de fournisseurs, pays d'origine, fabricants, concurrents, noms de boutiques
❌ Superlatifs non étayés (meilleur, inégalé, révolutionnaire...)
❌ Claims médicaux ou juridiques
❌ Emojis, MAJUSCULES excessives, style publicitaire agressif

RÈGLES GRAS :
- 6-10 phrases complètes importantes pour le client en <strong>, réparties dans TOUT le contenu
- Mettre en gras les phrases qui répondent à une question ou une inquiétude du client
- Ex : <strong>Elle s'adapte à tous les types de chambre et ne chauffe pas.</strong>
- Ex : <strong>Votre enfant peut l'utiliser en toute sécurité toute la nuit.</strong>
- Ce sont des PHRASES ENTIÈRES, pas juste des mots ou groupes de mots

STRUCTURE OBLIGATOIRE (8 H2, dans cet ordre) :

<p>Introduction 2-3 phrases : présente la collection "{collection_name}", le bénéfice principal pour le client. Contient <strong>{collection_name}</strong>.</p>

<h2>{niche_keyword} [angle sensoriel ou fonctionnel] : [accroche bénéfice client]</h2>
<p>Paragraphe 200+ mots. Répond à : pourquoi ce produit répond au besoin du client ? Utilise un vocabulaire évocateur (ex: sentinelle, gardienne, compagnon...). Ton narratif, pas de liste.</p>

<h2>[variation long-tail] : [angle multifonction ou design]</h2>
<p>Paragraphe 200+ mots. Répond à : à quoi sert-il concrètement, jour et nuit ? Esthétisme, praticité, rituel.</p>
<ul><li>Bénéfice client concis 1</li><li>Bénéfice client concis 2</li><li>Bénéfice client concis 3</li><li>Bénéfice client concis 4</li></ul>

<h2>[variation technologie] : [angle sécurité ou fiabilité]</h2>
<p>Paragraphe 200+ mots. Répond à : est-ce sûr pour mon enfant/usage ? Technologie, durabilité, économie.</p>
<ul><li>...</li><li>...</li><li>...</li><li>...</li></ul>

<h2>[variation feature spéciale] : [angle personnalisation ou options]</h2>
<p>Paragraphe 200+ mots. Répond à : quelles options s'adaptent à mes besoins ? Différents modes, réglages, polyvalence.</p>
<ul><li>...</li><li>...</li><li>...</li><li>...</li></ul>

<h2>[variation usage nomade ou pratique] : [angle praticité ou mobilité]</h2>
<p>Paragraphe 200+ mots. Répond à : puis-je l'utiliser partout ? Portabilité, autonomie, adaptation au quotidien.</p>
<ul><li>...</li><li>...</li><li>...</li><li>...</li></ul>

<h2>[variation expérience visuelle ou sensorielle] : [angle magie ou immersion]</h2>
<p>Paragraphe 200+ mots. Répond à : quelle expérience offre-t-il ? Ambiance, atmosphère, magie sensorielle. Ton narratif, pas de liste.</p>

<h2>[variation comparaison ou usage complémentaire]</h2>
<p>Paragraphe 200+ mots. Répond à : dans quel contexte l'utiliser ? Comparaison avec l'usage sans le produit, complémentarité.</p>

<h2>Pourquoi choisir {collection_name} ?</h2>
<p>Paragraphe synthèse 150+ mots. Résume les angles précédents, réassure le client sur son choix. Rappelle <strong>{collection_name}</strong>.</p>
<ul><li>Argument décisif 1</li><li>Argument décisif 2</li><li>Argument décisif 3</li><li>Argument décisif 4</li><li>Argument décisif 5</li></ul>

RÈGLES FINALES :
- MINIMUM 1000 mots au total
- Chaque H2 titre = "{niche_keyword} [variante]" ou "[variante] {niche_keyword}" pour le SEO
- Chaque H2 suit le format : mot-clé long-tail : sous-titre bénéfice client
- Contenu 100% original, centré sur les besoins et questions du client

Retourne UNIQUEMENT le HTML. Commence par <p>, termine par </p> ou </ul>.
"""


def build_collection_meta_title_prompt(collection_name, niche_keyword, tags, seo_keywords=""):
    """
    Construit le prompt pour générer le meta title d'une page collection.
    Même structure que build_boost_meta_prompt (SEO Boost), adapté collections.

    Args:
        collection_name : nom de la collection
        niche_keyword   : mot-clé de niche
        tags            : liste de tags
        seo_keywords    : bloc keywords SEO formaté (peut être vide)

    Returns:
        str : prompt complet pour OpenAI
    """
    tags_str = ", ".join(tags)

    seo_keywords_block = ""
    if seo_keywords and seo_keywords.strip():
        seo_keywords_block = f"""
{seo_keywords.strip()}

→ Intègre naturellement les termes SEO les plus pertinents dans le meta title.
"""

    return f"""Générateur meta title SEO orienté CTR (taux de clic). Réponds UNIQUEMENT en JSON.

COLLECTION : "{collection_name}"
NICHE : "{niche_keyword}"
MOTS-CLÉS CIBLÉS : "{tags_str}"
{seo_keywords_block}
OBJECTIF : Maximiser le taux de clic dans Google. L'utilisateur doit se dire "c'est exactement ce que je cherche".

STRUCTURE OBLIGATOIRE :
1. Commencer par "{niche_keyword}" + caractéristique principale de la collection
2. Ajouter un attribut de valeur (ex: XXL, Design, Maine Coon, Plafond)
3. Naturel, percutant, orienté CTR Google

RÈGLES :
- 60-70 caractères maximum
- Inclure les mots-clés SEO à fort volume si pertinents
- NE PAS inclure le nom de la boutique
- Si trop long : REFORMULER (ne pas tronquer)

{INTERDICTIONS}

FORMAT : {{"meta_title":"Ton titre ici"}}

Retourne UNIQUEMENT ce JSON.
"""


def build_collection_meta_desc_prompt(collection_name, niche_keyword, tags, seo_keywords=""):
    """
    Construit le prompt pour générer la meta description d'une page collection.
    Même structure que build_boost_meta_prompt (SEO Boost), adapté collections.

    Args:
        collection_name : nom de la collection
        niche_keyword   : mot-clé de niche
        tags            : liste de tags
        seo_keywords    : bloc keywords SEO formaté (peut être vide)

    Returns:
        str : prompt complet pour OpenAI
    """
    tags_str = ", ".join(tags)

    seo_keywords_block = ""
    if seo_keywords and seo_keywords.strip():
        seo_keywords_block = f"""
{seo_keywords.strip()}

→ Intègre naturellement les termes SEO les plus pertinents dans la meta description.
"""

    return f"""Générateur meta description SEO orientée CTR (taux de clic). Réponds UNIQUEMENT en JSON.

COLLECTION : "{collection_name}"
NICHE : "{niche_keyword}"
MOTS-CLÉS CIBLÉS : "{tags_str}"
{seo_keywords_block}
OBJECTIF : Maximiser le taux de clic dans Google. L'utilisateur doit se dire "c'est exactement ce que je cherche".

STRUCTURE OBLIGATOIRE :
1. Commencer par "{niche_keyword}" + caractéristique principale de la collection
2. Ajouter un bénéfice concret (choix, sélection, variété, qualité)
3. Terminer par un CTA (Découvrez, Explorez, Commandez)

RÈGLES :
- ~155 chars, phrase complète et naturelle
- Inclure les mots-clés SEO à fort volume si pertinents
- Si trop long : REFORMULER (ne pas tronquer)

{INTERDICTIONS}

FORMAT : {{"meta_description":"Ta description ici"}}

Retourne UNIQUEMENT ce JSON.
"""
