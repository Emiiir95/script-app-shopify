#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
generator.py — Fond Studio : régénération de la 1ère image via OpenAI gpt-image-1.

Pipeline par image :
  1. download_image(url)                → télécharge la photo produit (bytes)
  2. regenerate_on_background(...)       → gpt-image-1 edit → nouvelle image (bytes PNG)

La photo produit est envoyée en pièce jointe à gpt-image-1 (images.edit) avec un
prompt strict : seul le fond change, le produit reste identique.
"""

import base64
import io
import os

import requests

from features.fond_studio.prompts import build_background_prompt
from utils.logger import log

IMAGE_MODEL = "gpt-image-1"


def download_image(url, timeout=30):
    """Télécharge une image depuis son URL et retourne les bytes bruts."""
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _guess_name(url):
    """Nom de fichier (avec extension) déduit de l'URL, pour la pièce jointe OpenAI."""
    path = url.split("?")[0]
    ext  = os.path.splitext(path)[1].lower()
    if ext not in (".png", ".jpg", ".jpeg", ".webp"):
        ext = ".png"
    return "produit" + ext


def regenerate_on_background(image_bytes, source_url, color, client,
                            size="1024x1024", output_format="png", quality="medium"):
    """
    Régénère l'image du produit sur un fond de couleur unie via gpt-image-1.

    Args:
        image_bytes   : bytes de la photo produit originale
        source_url    : URL d'origine (sert juste à déduire le nom/extension)
        color         : couleur du fond (nom ou hex)
        client        : instance openai.OpenAI
        size          : "1024x1024" | "1536x1024" | "1024x1536" | "auto"
        output_format : "png" | "jpeg" | "webp" — format de l'image de sortie
        quality       : qualité gpt-image-1 (fixée à "medium" = normal côté appli)

    Returns:
        bytes : nouvelle image au format demandé
    """
    prompt = build_background_prompt(color)
    buf = io.BytesIO(image_bytes)
    buf.name = _guess_name(source_url)

    resp = client.images.edit(
        model=IMAGE_MODEL,
        image=buf,
        prompt=prompt,
        size=size,
        quality=quality,
        output_format=output_format,
    )
    b64 = resp.data[0].b64_json
    log(f"Fond Studio — image régénérée (fond: {color!r}, {size}, {output_format})")
    return base64.b64decode(b64)
