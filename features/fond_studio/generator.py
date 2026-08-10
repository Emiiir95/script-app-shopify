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


def make_image_buffer(image_bytes, source_url):
    """Construit un buffer nommé (BytesIO) prêt à être envoyé à OpenAI images.edit."""
    buf = io.BytesIO(image_bytes)
    buf.name = _guess_name(source_url)
    return buf


def regenerate_on_background(image_buffers, prompt, client,
                            size="1024x1024", output_format="png", quality="medium"):
    """
    Régénère l'image du produit selon le prompt fourni (fond couleur ou mise en scène).

    Args:
        image_buffers : liste de BytesIO nommés (>= 1). Une seule → édition simple ;
                        plusieurs → toutes servent de référence (angles) pour + de fidélité.
        prompt        : prompt d'édition déjà construit (voir prompts.py)
        client        : instance openai.OpenAI
        size          : "1024x1024" | "1536x1024" | "1024x1536" | "auto"
        output_format : "png" | "jpeg" | "webp" — format de l'image de sortie
        quality       : qualité gpt-image-1 (fixée à "medium" = normal côté appli)

    Returns:
        bytes : nouvelle image au format demandé
    """
    # gpt-image-1 accepte un seul fichier OU une liste (références multiples)
    image_arg = image_buffers if len(image_buffers) > 1 else image_buffers[0]

    resp = client.images.edit(
        model=IMAGE_MODEL,
        image=image_arg,
        prompt=prompt,
        size=size,
        quality=quality,
        output_format=output_format,
    )
    b64 = resp.data[0].b64_json
    log(f"Fond Studio — image régénérée ({len(image_buffers)} réf, {size}, {output_format})")
    return base64.b64decode(b64)
