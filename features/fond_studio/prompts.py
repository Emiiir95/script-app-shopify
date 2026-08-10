#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
prompts.py — Prompts de retouche pour la feature Fond Studio.

Deux types de fond :
  - couleur unie  → build_background_prompt(color)
  - mise en scène → build_scene_prompt(scene_key)  (templates par niche/style)

Dans les deux cas, les MÊMES règles s'appliquent au produit : 100 % identique,
recentré, ombre de contact douce, aucun texte/objet ajouté.
"""

# Règles communes : le produit ne change JAMAIS (copie fidèle), il est juste recentré.
_RULES = (
    "This is STRICTLY a background-replacement task. Preserve the product with the highest "
    "possible fidelity — keep it PIXEL-FOR-PIXEL IDENTICAL to the original: exact same shape, "
    "outline, silhouette, size, proportions, viewing angle, colors, materials, textures, "
    "patterns, reflections, highlights, printed text, labels, logos, stitching, seams, "
    "engravings and every tiny detail. Do NOT repaint, redraw, restyle, smooth, sharpen, "
    "denoise, beautify, upscale, recolor, relight or reinterpret ANY part of the product — "
    "copy it exactly as it is, like a cut-and-paste of the original pixels. You may ONLY "
    "reposition and uniformly scale the product AS A SINGLE WHOLE to center it in the frame "
    "with even margins — never crop, deform, rotate or modify it. Change ONLY the background. "
    "Add soft natural lighting and a subtle realistic contact shadow directly under the "
    "product. No added text, no logo overlay, no props, no extra objects. Output only the "
    "exact original product, centered, on the new background."
)


def _wrap(background_desc):
    """Assemble le prompt : remplacer le fond par {background_desc} + règles produit."""
    return f"Edit the attached product photo. Replace the background with {background_desc}. " + _RULES


# ── Fond couleur unie ───────────────────────────────────────────────────────────

def _hex_to_rgb(color):
    """'#F7F7F7' | 'F7F7F7' → (247, 247, 247). Retourne None si ce n'est pas un hex."""
    if not color:
        return None
    c = color.strip().lstrip("#")
    if len(c) == 3:                       # forme courte #abc → #aabbcc
        c = "".join(ch * 2 for ch in c)
    if len(c) != 6:
        return None
    try:
        return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))
    except ValueError:
        return None


def build_background_prompt(color):
    """
    Prompt pour un fond de couleur unie (hex ou nom).

    Objectif : que gpt-image-1 respecte EXACTEMENT la couleur demandée et produise
    un fond parfaitement uniforme, identique d'une image à l'autre. On répète la
    valeur (hex + RGB), on interdit explicitement toute dérive/gradient/vignette.
    """
    color = (color or "white").strip()
    rgb   = _hex_to_rgb(color)

    if rgb:
        hexv  = "#" + "".join(f"{v:02X}" for v in rgb)
        spec  = f"EXACTLY the color {hexv} (sRGB {rgb[0]},{rgb[1]},{rgb[2]})"
        drift = (f"Do NOT drift to a different shade — not pure white, not grey, not cream, "
                 f"not off-white — reproduce {hexv} precisely.")
    else:
        spec  = f"EXACTLY the solid color '{color}'"
        drift = f"Do NOT drift to a different shade — reproduce '{color}' precisely."

    background_desc = (
        f"a single, perfectly FLAT, UNIFORM, SEAMLESS solid fill of {spec}, covering 100% of "
        f"the frame edge to edge and in every corner. The background must be this one constant "
        f"color value everywhere, with ZERO gradient, ZERO vignette, ZERO lighting falloff, "
        f"ZERO color-temperature shift, no texture, no pattern, no reflection and no ambient "
        f"tint. {drift} Keep this background color IDENTICAL and repeatable across different "
        f"photos so a whole catalog processed this way shares the exact same backdrop"
    )
    # Pour un fond couleur, l'ombre de contact doit rester minuscule pour ne pas
    # casser l'uniformité : on remplace la règle d'ombre générique.
    color_shadow_note = (
        " If any contact shadow is added, keep it extremely subtle, small and directly under "
        "the product only; the rest of the background stays perfectly uniform at the given color."
    )
    return _wrap(background_desc) + color_shadow_note


# ── Mises en scène (templates par niche / style) ────────────────────────────────

SCENE_TEMPLATES = {
    "minimaliste": {"label": "Minimaliste / épuré",
                    "scene": "a clean minimalist scene: a smooth light neutral surface with soft even studio lighting and generous empty space"},
    "luxe":        {"label": "Luxe / premium",
                    "scene": "an elegant luxury scene: a polished marble surface with soft warm golden lighting and a refined premium atmosphere"},
    "mode":        {"label": "Mode / fashion",
                    "scene": "a stylish fashion-editorial studio scene with a soft neutral gradient backdrop and trendy clean lighting"},
    "nature":      {"label": "Nature / bois",
                    "scene": "a natural organic scene: a light wooden surface with a few soft green leaves and warm daylight"},
    "beaute":      {"label": "Beauté / cosmétique",
                    "scene": "a bright beauty scene: a clean pastel surface with soft reflections and delicate lighting"},
    "maison":      {"label": "Maison / déco",
                    "scene": "a cozy home-decor scene: a warm wooden table in a softly lit interior"},
    "tech":        {"label": "Tech / moderne",
                    "scene": "a sleek modern tech scene: a smooth surface with cool clean lighting and a futuristic minimal feel"},
    "cuisine":     {"label": "Cuisine / food",
                    "scene": "a warm kitchen scene: a clean kitchen counter with soft natural daylight"},
    "enfant":      {"label": "Enfant / kids",
                    "scene": "a playful kids scene: soft pastel colors with a gentle cheerful atmosphere"},
    "sport":       {"label": "Sport / dynamique",
                    "scene": "a dynamic sport scene: a textured concrete urban surface with energetic directional lighting"},
}


def build_scene_prompt(scene_key):
    """Prompt pour une mise en scène prédéfinie (fallback minimaliste si clé inconnue)."""
    tpl = SCENE_TEMPLATES.get(scene_key) or SCENE_TEMPLATES["minimaliste"]
    return _wrap(tpl["scene"])
