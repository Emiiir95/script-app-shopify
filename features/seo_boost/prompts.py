#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompts.py — Prompts OpenAI pour la feature SEO Boost.

Portage exact des fonctions JS de prompts-boost.js :
  - build_boost_ai_branding_prompt    → buildBoostAIBrandingPrompt
  - build_boost_meta_prompt           → buildBoostMetaPrompt
  - build_boost_differentiator_prompt → buildBoostDifferentiatorPrompt
  - build_boost_description_prompt    → buildBoostDescriptionPrompt

La constante INTERDICTIONS est partagée par tous les prompts.
"""

INTERDICTIONS = """❌ Pays d'origine, marques, fabricants
❌ garantie, garanti, offre, promo, gratuit, livraison"""


def build_boost_ai_branding_prompt(product_keyword, niche_keyword, supplier_description):
    """
    Construit le prompt pour générer un nom de modèle créatif unique (mode "ai").
    Port exact de buildBoostAIBrandingPrompt (prompts-boost.js).

    Args:
        product_keyword      : mot-clé principal du produit
        niche_keyword        : mot-clé de niche
        supplier_description : description brute du fournisseur (peut être vide)

    Returns:
        str : prompt complet pour OpenAI
    """
    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""DESCRIPTION FOURNISSEUR :
\"\"\"
{supplier_description.strip()}
\"\"\"
"""

    return f"""Expert naming/branding. Invente UN nom de modèle créatif pour ce produit.

PRODUIT : "{product_keyword}"
NICHE : "{niche_keyword}"

{supplier_block}
RÈGLES :
- UN SEUL mot inventé (ou deux fusionnés), 4-12 chars
- Prononçable, mémorable, style premium
- Peut mélanger syllabes de mots liés au produit
- PAS un mot existant, PAS le nom du produit/niche
- Ex: lumineux→"LumiNest", coussin→"Plumea", étagère→"Skala"

Retourne UNIQUEMENT le nom, sans guillemets.
"""


def build_boost_meta_prompt(product_keyword, niche_keyword, supplier_description, seo_keywords=""):
    """
    Construit le prompt pour générer la meta description SEO.
    Port exact de buildBoostMetaPrompt (prompts-boost.js).

    Args:
        product_keyword      : mot-clé principal du produit
        niche_keyword        : mot-clé de niche
        supplier_description : description brute du fournisseur (peut être vide)
        seo_keywords         : bloc keywords SEO formaté (peut être vide)

    Returns:
        str : prompt complet pour OpenAI
    """
    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""CONTEXTE FOURNISSEUR :
\"\"\"
{supplier_description.strip()}
\"\"\"
"""

    seo_keywords_block = ""
    if seo_keywords and seo_keywords.strip():
        seo_keywords_block = f"""
{seo_keywords.strip()}

→ Intègre naturellement les termes SEO les plus pertinents dans la meta description.
"""

    return f"""Générateur meta description SEO orientée CTR (taux de clic). Réponds UNIQUEMENT en JSON.

PRODUIT : "{product_keyword}"
NICHE : "{niche_keyword}"
{supplier_block}{seo_keywords_block}
OBJECTIF : Maximiser le taux de clic dans Google. L'utilisateur doit se dire "c'est exactement ce que je cherche".

STRUCTURE OBLIGATOIRE :
1. Commencer par "{niche_keyword}" + caractéristique principale (dimensions, feature)
2. Ajouter un bénéfice concret (confort, solidité, praticité)
3. Terminer par un CTA (Livraison rapide, Découvrez, Commandez)

RÈGLES :
- ~155 chars, phrase complète et naturelle
- Inclure les mots-clés SEO à fort volume si pertinents
- Si trop long : REFORMULER (ne pas tronquer)

{INTERDICTIONS}

FORMAT : {{"description":"Ta description ici"}}

Retourne UNIQUEMENT ce JSON.
"""


def build_boost_differentiator_prompt(product_keyword, niche_keyword, supplier_description, seo_keywords=""):
    """
    Construit le prompt pour générer les attributs différenciants d'un produit.
    Port exact de buildBoostDifferentiatorPrompt (prompts-boost.js).

    Args:
        product_keyword      : mot-clé principal du produit
        niche_keyword        : mot-clé de niche
        supplier_description : description brute du fournisseur (peut être vide)
        seo_keywords         : bloc keywords SEO formaté (peut être vide)

    Returns:
        str : prompt complet pour OpenAI
    """
    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""DESCRIPTION FOURNISSEUR :
\"\"\"
{supplier_description.strip()}
\"\"\"
"""

    seo_keywords_block = ""
    if seo_keywords and seo_keywords.strip():
        seo_keywords_block = f"\n{seo_keywords.strip()}"

    return f"""Expert SEO e-commerce / Google Shopping. Génère les attributs différenciants pour "{product_keyword}".

{supplier_block}
NICHE : "{niche_keyword}"
{seo_keywords_block}
STRUCTURE OBLIGATOIRE (dans cet ordre de priorité) :
1. Keyword commercial à fort volume (ex: XXL, Plafond, Design, Maine Coon, Mural)
2. Taille/dimensions si disponible (ex: 180cm, 114cm)
3. Feature principale (ex: Hamac, Griffoir, Niche)
4. Style/matériau (ex: Bois, Sisal, Moderne)

RÈGLES :
- Max 5-6 mots, PAS de phrase
- UTILISER les termes des KEYWORDS AUTORISÉS ci-dessus (si fournis)
- Placer le keyword commercial LE PLUS RECHERCHÉ en PREMIER
- La couleur va en DERNIER (faible volume SEO)
- Ex: "XXL 180cm Hamac Bois Design", "Plafond Réglable Hamac Bois", "Design Bois Massif Moderne"

Retourne UNIQUEMENT les attributs en une ligne.
"""


def build_boost_description_prompt(product_keyword, niche_keyword, supplier_description, branding_name="", word_count=200, seo_keywords="", collections=None):
    """
    Construit le prompt pour générer une description HTML SEO.
    Port exact de buildBoostDescriptionPrompt (prompts-boost.js).

    Args:
        product_keyword      : mot-clé principal du produit (H1 avec branding)
        niche_keyword        : mot-clé de niche
        supplier_description : description brute du fournisseur (peut être vide)
        branding_name        : nom de modèle branding (peut être vide)
        word_count           : nombre minimum de mots (clamped 200-400)
        seo_keywords         : bloc keywords SEO formaté (peut être vide)
        collections          : liste de dicts {name, url, volume} pour le maillage interne

    Returns:
        str : prompt complet pour OpenAI
    """
    wc = max(200, min(400, int(word_count) if str(word_count).isdigit() else 200))

    branding_block = ""
    if branding_name and branding_name.strip():
        branding_block = f'NOM DE MODÈLE BRANDING : "{branding_name}" - Intègre-le naturellement.\n'

    supplier_block = ""
    if supplier_description and supplier_description.strip():
        supplier_block = f"""DESCRIPTION FOURNISSEUR À REFORMULER :
\"\"\"
{supplier_description.strip()}
\"\"\"

Utilise ces informations pour créer une description ORIGINALE et REFORMULÉE.
"""

    seo_keywords_block = ""
    if seo_keywords and seo_keywords.strip():
        seo_keywords_block = f"""
{seo_keywords.strip()}
→ Utilise ces termes SEO naturellement dans les H2, H3 et le contenu.
"""

    # ── Maillage interne (port exact du JS) ──────────────────────────────────
    valid_collections = [c for c in (collections or []) if c.get("url")]
    has_collections   = len(valid_collections) > 0
    link_count        = len(valid_collections)
    s                 = "s" if link_count > 1 else ""

    maillage_block = ""
    structure_maillage_line = ""
    if has_collections:
        col_list = "\n".join(
            f"- {c.get('name', 'Collection')} → {c['url']}"
            for c in valid_collections
        )
        maillage_block = f"""
MAILLAGE INTERNE (OBLIGATOIRE) :
Un dernier paragraphe avec EXACTEMENT {link_count} lien{s} vers ces collections.
Utilise les URLs COMPLÈTES telles quelles (avec le domaine).
Format : <a href="URL_COMPLÈTE" target="_blank" rel="noopener">texte ancre naturel</a>

Collections à lier :
{col_list}

RÈGLES MAILLAGE :
- EXACTEMENT {link_count} lien{s}, pas plus, pas moins
- Le 1er lien pointe vers la collection principale (volume max)
- Ancres naturelles intégrées dans une ou deux phrases (pas de liste)
- URLs COMPLÈTES avec https:// (anti-scraping)
- Varier les textes d'ancre (ne pas répéter le même mot-clé)
"""
        structure_maillage_line = f"\n<p>Paragraphe maillage avec {link_count} liens collections.</p>"

    return f"""RÔLE : Générateur fiches produits e-commerce SEO. Réponds UNIQUEMENT en HTML pur.

⚠️ HTML uniquement : <strong> pour le gras (JAMAIS **), <h2>/<h3> pour titres (JAMAIS #)

PRODUIT : "{product_keyword}"
NICHE : "{niche_keyword}"
LONGUEUR : MIN {wc} mots
{branding_block}
{supplier_block}{seo_keywords_block}
RÈGLES :
- "{product_keyword}" en <strong> UNE FOIS dans les 100 premiers mots
- GRAS : 5-8 groupes courts (2-6 mots) en <strong> répartis dans toute la description : dimensions, matériaux, caractéristiques techniques, bénéfices concrets, capacités d'usage
- Structure : 1 H2 tous les 200-250 mots, 1-3 H3 sous chaque H2
- Paragraphes ≤ 3 lignes, contenu 100% original, ton factuel et clair

{INTERDICTIONS}
❌ Superlatifs non étayés, claims médicaux/juridiques
❌ Style publicitaire agressif, emojis, MAJUSCULES excessives

STRUCTURE :
<p>Introduction avec <strong>{product_keyword}</strong> en gras.</p>
<h2>Titre avec "{product_keyword}"</h2>
<p>Accroche.</p>
<h3>Pourquoi choisir {product_keyword} ?</h3>
<ul><li>bénéfice 1</li><li>bénéfice 2</li><li>bénéfice 3</li><li>bénéfice 4</li><li>bénéfice 5</li></ul>
<h3>Titre CTA</h3>
<p>Paragraphe CTA.</p>{structure_maillage_line}
{maillage_block}
Retourne UNIQUEMENT le HTML. Commence par <p>, termine par </p>.
"""
