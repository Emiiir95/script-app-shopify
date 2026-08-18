#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompts.py — Feature Balises : prompt de classement d'un produit dans les collections.

L'IA reçoit le contenu RÉEL du produit (titre, description, type, caractéristiques,
tags actuels) et la liste RÉELLE des collections de la boutique (récupérées en direct
depuis Shopify). Elle renvoie les collections auxquelles le produit appartient VRAIMENT.
"""


def build_classification_prompt(product_ctx, collections, max_collections=0):
    """
    Construit le prompt de classement.

    Args:
        product_ctx     : dict { title, description, product_type, caracteristiques, tags }
        collections     : list de dicts { handle, title, description } (collections réelles)
        max_collections : plafond de collections par produit (0 = aucun plafond)

    Returns:
        str : prompt complet. L'IA doit répondre en JSON {"collections": ["handle", ...]}.
    """
    title   = (product_ctx.get("title") or "").strip()
    desc    = (product_ctx.get("description") or "").strip()[:1200]
    ptype   = (product_ctx.get("product_type") or "").strip()
    caract  = (product_ctx.get("caracteristiques") or "").strip()[:800]
    tags    = product_ctx.get("tags") or ""
    if isinstance(tags, (list, tuple)):
        tags = ", ".join(tags)

    lines = [f'- {c["handle"]} : "{c.get("title", "")}"'
             + (f' — {(c.get("description") or "").strip()[:160]}' if c.get("description") else "")
             for c in collections]
    collections_block = "\n".join(lines)

    ptype_block  = f"\nTYPE : {ptype}" if ptype else ""
    caract_block = f'\nCARACTÉRISTIQUES :\n"""\n{caract}\n"""' if caract else ""
    tags_block   = f"\nTAGS ACTUELS : {tags}" if tags else ""

    if max_collections and max_collections > 0:
        cap_rule = (f"- Choisis AU PLUS {max_collections} collection(s), les plus pertinentes. "
                    "Si moins conviennent, en mettre moins ; si aucune, liste vide.")
    else:
        cap_rule = ("- Choisis TOUTES les collections qui correspondent vraiment "
                    "(pas de limite). Si aucune ne convient, liste vide.")

    return f"""Expert e-commerce. Classe ce produit dans les BONNES collections de la boutique.

PRODUIT
TITRE : "{title}"{ptype_block}
DESCRIPTION :
\"\"\"
{desc}
\"\"\"{caract_block}{tags_block}

COLLECTIONS DISPONIBLES (identifiant : nom — description) :
{collections_block}

RÈGLES :
- Ne choisis QUE des collections dont le produit fait RÉELLEMENT partie (un vrai acheteur
  s'attendrait à l'y trouver). Base-toi sur le contenu du produit, pas sur des suppositions.
- Recopie EXACTEMENT les identifiants (handles) de la liste ci-dessus, rien d'inventé.
{cap_rule}
- Ne te limite pas au thème général : une collection « couleur », « taille » ou « usage »
  compte aussi si le produit correspond.

Réponds UNIQUEMENT en JSON : {{"collections": ["handle-1", "handle-2"]}}
"""
