#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompts.py — Prompt de retouche pour la feature Fond Studio.

Un seul prompt : demander à gpt-image-1 de remplacer UNIQUEMENT le fond de la
photo produit par une couleur unie, en gardant le produit strictement identique.
"""


def build_background_prompt(color):
    """
    Construit le prompt d'édition d'image pour un fond de couleur unie.

    Args:
        color : couleur voulue (nom ou hex), ex: "blanc", "beige", "#F5F5F5"

    Returns:
        str : prompt en anglais (meilleurs résultats sur les modèles image)
    """
    color = (color or "white").strip()
    return (
        "Edit the attached product photo. Replace the background with a plain, uniform, "
        f"solid {color} background (clean studio look). "
        "Keep the PRODUCT ITSELF 100% identical to the original: exact same shape, size, "
        "proportions, colors, materials, textures, patterns, viewing angle, logos and every "
        "detail — do NOT redesign, regenerate, add, remove or alter any part of the product. "
        "Reposition the product so it is PERFECTLY CENTERED in the frame, with even margins on "
        "all sides. You may move and scale the product AS A WHOLE only to center it — never "
        "change its appearance. Soft natural studio lighting with a subtle realistic contact "
        "shadow under the product. No text, no logos overlay, no props, no extra objects — "
        f"only the centered product on a solid {color} background."
    )
