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


# Types d'attributs pouvant composer le titre produit (differentiator).
# L'utilisateur coche/décoche chacun via config.json > seo_boost.title_attributes.
# (clé, libellé prompt avec exemples). L'ordre = ordre de priorité dans le titre.
TITLE_ATTRIBUTES = [
    ("commercial_keyword", "Mot-clé commercial à fort volume (ex: XXL, Plafond, Design, Mural)"),
    ("dimensions",         "Taille / dimensions (ex: 180cm, 114cm, 10cm)"),
    ("feature",            "Fonction principale (ex: Musicale, Rangement, Hamac, Griffoir)"),
    ("material",           "Matériau (ex: Bois, Sisal, Cuir, Velours)"),
    ("style",              "Style (ex: Moderne, Design, Élégant)"),
    ("color",              "Couleur (ex: Beige, Noir, Rose)"),
]


def build_natural_title_prompt(product_title, supplier_description, niche, title_attributes=None,
                               branding_name="", branding_position="start", title_style="characteristics",
                               avoid=None, seo_keywords=""):
    """
    Prompt pour un H1 + meta title NATURELS (best practices 2026) : écrit pour l'acheteur,
    mot-clé en tête quand c'est fluide, sinon le vrai nom du produit (« Support Collier »).
    Pas de mots-clés empilés. N'utilise QUE les attributs cochés. Cible les mots-clés
    RÉELLEMENT recherchés (volumes SEMrush) s'ils sont fournis. Retour JSON {h1, meta_title}.
    """
    desc = (supplier_description or "").strip()[:600]
    desc_block = f'DESCRIPTION FOURNISSEUR :\n"""\n{desc}\n"""\n' if desc else ""

    seo_block = ""
    if seo_keywords and seo_keywords.strip():
        seo_block = (
            "\nMOTS-CLÉS RÉELLEMENT RECHERCHÉS SUR GOOGLE (par volume — les acheteurs tapent ça) :\n"
            + seo_keywords.strip()
            + "\n→ Intègre NATURELLEMENT les termes à FORT VOLUME qui décrivent vraiment ce produit ; "
              "place le plus recherché le plus tôt possible.\n"
        )

    attrs    = resolve_title_attributes(title_attributes)
    included = [label for key, label in TITLE_ATTRIBUTES if attrs[key]]
    excluded = [label for key, label in TITLE_ATTRIBUTES if not attrs[key]]
    inc_block = "\n".join(f"- {l}" for l in included) if included else "- (aucun attribut)"
    exc_line  = (" ; ".join(l.split(" (")[0] for l in excluded)) if excluded else "aucun"

    branding_instr = ""
    if title_style in ("branded", "seo_branded") and branding_name:
        if branding_position == "end":
            branding_instr = f'\nMARQUE : intègre "{branding_name}" à la FIN, format « … – {branding_name} ».'
        else:
            branding_instr = f'\nMARQUE : intègre "{branding_name}" au DÉBUT, format « {branding_name} – … ».'

    avoid_block = ""
    if avoid:
        lst = "\n".join(f'- "{t}"' for t in list(avoid)[:10])
        avoid_block = ("\n⚠️ CES TITRES SONT DÉJÀ PRIS — produis un H1 DIFFÉRENT (autre formulation, "
                       "autres synonymes), sans sortir des attributs autorisés :\n" + lst + "\n")

    return f"""Expert SEO e-commerce. Rédige le TITRE PRODUIT (H1) et le META TITLE, NATURELS et optimisés Google.

TITRE FOURNISSEUR : "{product_title}"
{desc_block}NICHE / CATÉGORIE (mot-clé principal) : "{niche}"
{seo_block}
ATTRIBUTS AUTORISÉS dans le titre (n'inclus QUE ceux qui existent vraiment pour ce produit) :
{inc_block}
NE PAS inclure : {exc_line}{branding_instr}{avoid_block}

OBJECTIF : qu'un acheteur qui cherche CE type de produit sur Google tombe sur celui-ci. Pense
aux mots qu'il tape vraiment. Cible l'INTENTION d'achat, pas juste la catégorie.

⚠️ VÉRITÉ PRODUIT (RÈGLE ABSOLUE) : la DESCRIPTION FOURNISSEUR est SOUVENT FAUSSE sur les matières.
Donc, si une PHOTO du produit est jointe :
- Pour la MATIÈRE et la COULEUR, IGNORE totalement ce que dit le texte — base-toi UNIQUEMENT sur ce
  que tu VOIS sur la photo (métal, plastique, bois, verre, velours…).
- N'écris une matière QUE si elle est clairement visible sur la photo. Dans le MOINDRE doute,
  N'EN METS AUCUNE (un titre sans matière vaut mieux qu'une matière fausse).
- N'invente jamais « bois », « cuir » ou autre juste parce que c'est écrit dans le texte ou recherché.
Sans photo : ne mentionne une matière que si la description est explicite et cohérente ; sinon, omets-la.

RÈGLES H1 :
- NATUREL et lisible, écrit pour l'acheteur — surtout PAS de mots-clés empilés ni de répétition
- Mets le mot-clé principal « {niche} » (ou le terme le plus recherché) en tête SI c'est fluide ;
  SINON utilise le vrai nom du produit (ex : « Support à Colliers » plutôt que « Porte Bijoux Support Collier »)
- Ajoute 1 à 2 précisions RECHERCHÉES et utiles (usage, cible, matière, forme) qui aident au référencement
  ET renseignent l'acheteur — sans bourrage
- N'écris JAMAIS d'abréviations ou de codes techniques dans le titre (« PU », « MDF », « PVC »…) :
  emploie un mot simple et naturel, ou omets-le. Choisis toi-même le terme courant le plus adapté
  (ex : « Cuir » au lieu de « Cuir PU »)
- BANNIS les adjectifs décoratifs SANS valeur de recherche (« élégant », « joli », « beau »,
  « magnifique », « superbe », « raffiné », « chic », « sublime »…) : ils gaspillent la place.
  Chaque mot doit aider à être TROUVÉ ou CLIQUÉ. Préfère un attribut CONCRET et recherché qui décrit
  une vraie caractéristique/usage (ex : « rotatif », « mural », « pliable », « à LED »,
  « grande capacité », « 3 tiroirs », « à clé ») — ou rien si tu n'en as pas
- Ne répète jamais deux fois la même idée
- 50 à 65 caractères (le H1 peut être un peu plus riche que le meta title)
- N'utilise QUE les types d'attributs autorisés ci-dessus, et seulement s'ils s'appliquent

RÈGLES META TITLE :
- Même SUJET et même mot-clé principal que le H1, MAIS formulé DIFFÉREMMENT — surtout PAS une
  copie mot pour mot du H1 (autre tournure, angle plus orienté clic)
- 50 à 60 caractères (longueur idéale Google, taux de réécriture le plus bas)
- Commence par le mot-clé le plus recherché ; orienté CTR (donne envie de cliquer)
- NE PAS mettre le nom de la boutique (Shopify l'ajoute automatiquement)

{INTERDICTIONS}

Réponds UNIQUEMENT en JSON : {{"h1":"...","meta_title":"..."}}
"""


def build_product_type_prompt(product_title, supplier_description, niche_keyword="", niches=None):
    """
    Prompt pour déterminer la NICHE/TYPE d'un produit (boutique thématique), à partir
    du titre + description fournisseur. Sert de base au H1 à la place de la niche fixe.

    Si `niches` (liste) est fourni : l'IA CHOISIT la meilleure niche DANS cette liste
    (classification). Sinon : elle propose librement un type en 2-4 mots.
    """
    desc = (supplier_description or "").strip()[:600]
    desc_block = f'DESCRIPTION FOURNISSEUR :\n"""\n{desc}\n"""\n' if desc else ""

    if niches:
        niche_list = "\n".join(f"- {n}" for n in niches if str(n).strip())
        hint = f'\nTHÈME GÉNÉRAL (indice) : "{niche_keyword}"' if niche_keyword else ""
        return f"""Expert e-commerce. Classe ce produit dans la BONNE catégorie de la boutique.

TITRE FOURNISSEUR : "{product_title}"
{desc_block}{hint}

CATÉGORIES DE LA BOUTIQUE (choisis-en UNE, celle qui décrit le mieux le produit) :
{niche_list}

RÈGLES :
- Choisis EXACTEMENT une des catégories ci-dessus, celle qui correspond au produit (titre + description)
- Recopie-la à l'identique (même orthographe)
- Si VRAIMENT aucune ne convient, propose le type le plus juste en 2-4 mots (sans attribut ni chiffre)

Retourne UNIQUEMENT la catégorie choisie, rien d'autre.
"""

    hint = f'\nTHÈME GÉNÉRAL DE LA BOUTIQUE (indice, PAS une obligation) : "{niche_keyword}"' if niche_keyword else ""
    return f"""Expert e-commerce. Donne UNIQUEMENT le TYPE de produit (sa catégorie générique) en 2 à 4 mots.

TITRE FOURNISSEUR : "{product_title}"
{desc_block}{hint}

RÈGLES :
- Le type = ce QU'EST vraiment le produit (ex: "Boîte à Montre", "Porte Bijoux", "Armoire à Bijoux", "Arbre à Bijoux", "Boîte à Bijoux")
- PAS d'attributs (taille, couleur, matière, style), PAS de marque, PAS de chiffres
- 2 à 4 mots maximum, au singulier
- Se baser sur le TITRE et la DESCRIPTION, pas sur le thème de la boutique

Retourne UNIQUEMENT le type, rien d'autre.
"""


def resolve_title_attributes(title_attributes):
    """
    Normalise la config title_attributes en dict {clé: bool}.
    Absent ou clé manquante → True (comportement historique : tout inclus).
    """
    cfg = title_attributes or {}
    return {key: bool(cfg.get(key, True)) for key, _ in TITLE_ATTRIBUTES}


def build_boost_differentiator_prompt(product_keyword, niche_keyword, supplier_description, seo_keywords="", title_attributes=None, avoid=None):
    """
    Construit le prompt pour générer les attributs différenciants d'un produit.

    Args:
        product_keyword      : mot-clé principal du produit
        niche_keyword        : mot-clé de niche
        supplier_description : description brute du fournisseur (peut être vide)
        seo_keywords         : bloc keywords SEO formaté (peut être vide)
        title_attributes     : dict {clé: bool} des attributs à inclure dans le titre
                               (voir TITLE_ATTRIBUTES). None = tout inclure.

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

    # Structure dynamique : seuls les attributs cochés sont inclus (dans l'ordre)
    attrs    = resolve_title_attributes(title_attributes)
    included = [label for key, label in TITLE_ATTRIBUTES if attrs[key]]
    excluded = [label for key, label in TITLE_ATTRIBUTES if not attrs[key]]

    structure_lines = "\n".join(f"{i+1}. {lbl}" for i, lbl in enumerate(included)) \
        if included else "(aucun attribut demandé — retourne une chaîne vide)"

    exclusion_block = ""
    if excluded:
        exclusion_block = (
            "\nNE PAS INCLURE ces attributs (l'utilisateur ne les veut PAS dans le titre) :\n"
            + "\n".join(f"- {lbl}" for lbl in excluded)
            + "\n"
        )

    color_rule = "\n- La couleur va en DERNIER (faible volume SEO)" if attrs["color"] else ""

    avoid_block = ""
    if avoid:
        lst = "\n".join(f'- "{t}"' for t in list(avoid)[:10])
        avoid_block = (
            "\n⚠️ CES COMBINAISONS SONT DÉJÀ PRISES par d'autres produits — tu DOIS en produire "
            "une DIFFÉRENTE (autres synonymes de style/mot-clé commercial, autre ordre, autre "
            "angle), en restant STRICTEMENT dans les attributs autorisés ci-dessus :\n"
            + lst + "\n"
        )

    return f"""Expert SEO e-commerce / Google Shopping. Génère les attributs différenciants pour "{product_keyword}".

{supplier_block}
NICHE : "{niche_keyword}"
{seo_keywords_block}
ATTRIBUTS À INCLURE (dans cet ordre de priorité) :
{structure_lines}
{exclusion_block}{avoid_block}
RÈGLES :
- Max 5-6 mots, PAS de phrase
- UTILISER les termes des KEYWORDS AUTORISÉS ci-dessus (si fournis)
- Placer le keyword commercial LE PLUS RECHERCHÉ en PREMIER
- N'inclure QUE les types d'attributs listés dans « ATTRIBUTS À INCLURE »{color_rule}
- Varie le vocabulaire (synonymes de style/mot-clé commercial) pour que deux produits
  similaires n'aient PAS le même libellé
- Ex: "XXL 180cm Hamac Bois Design", "Plafond Réglable Hamac Bois"

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
