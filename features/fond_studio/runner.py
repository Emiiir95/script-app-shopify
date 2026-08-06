#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration Fond Studio.

Régénère la 1ère image de chaque produit sur un fond de couleur unie (via gpt-image-1)
et l'ajoute en position 1 (l'ancienne 1ère image est conservée, juste décalée après).

Flow :
  1. Lit la config "fond_studio" (background_color, size, quality)
  2. Connexion Shopify + OpenAI
  3. Récupère les produits avec images
  4. Résumé + confirmation
  5. Pour chaque produit : télécharge la 1ère image → régénère sur fond uni → ajoute en position 1
  6. Checkpoint après chaque produit (reprise auto) + rapport CSV

Config config.json :
  "fond_studio": {
    "background_color": "#FFFFFF",   // hex (via palette) ou nom, ex: "beige"
    "size":           "1024x1024",   // optionnel
    "output_format":  "png",         // optionnel : png | jpeg | webp
    "product_status": "all"          // optionnel : all | active | draft (sinon demandé au lancement)
  }
"""

import sys

from openai import OpenAI
from tqdm import tqdm

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from shopify.products import fetch_all_products_with_images
from features.fond_studio.generator import download_image, regenerate_on_background
from features.fond_studio.injector import add_first_image, generate_injection_report
from utils.logger import log, LOG_FILE
from utils.checkpoint import save_progress, load_progress, clear_progress
from utils.product_filter import ask_product_status

# Prix indicatif gpt-image-1 par image générée (qualité medium) — USD.
# À vérifier sur https://openai.com/api/pricing (peut évoluer).
_PRICE_PER_IMAGE   = {"1024x1024": 0.042, "1024x1536": 0.063, "1536x1024": 0.063, "auto": 0.042}
_INPUT_IMAGE_COST  = 0.012   # ~ coût de la photo d'entrée envoyée à l'édition


def _estimate_cost(n_images, size):
    """Estimation du coût OpenAI total (USD) pour n images."""
    per = _PRICE_PER_IMAGE.get(size, 0.042) + _INPUT_IMAGE_COST
    return n_images * per, per


def run(store_config, store_path):
    """
    Point d'entrée de la feature Fond Studio.

    Args:
        store_config : dict { name, store_url, access_token, openai_key, fond_studio: {...} }
        store_path   : chemin absolu vers stores/{boutique}/
    """
    store_name = store_config.get("name", "boutique")
    cfg           = store_config.get("fond_studio", {})
    color         = (cfg.get("background_color") or "").strip()
    size          = cfg.get("size", "1024x1024")
    output_format = cfg.get("output_format", "png")
    quality       = "medium"   # qualité normale, fixe

    log("=" * 60)
    log(f"Démarrage feature Fond Studio — boutique : {store_name}")
    print("=" * 60)
    print(f"  Fond Studio — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    if not color:
        print("\n[INFO] Aucune couleur de fond définie dans config.json.")
        print('  → Ajoutez "fond_studio": { "background_color": "blanc" } dans votre config.json')
        return

    # ── Connexion ─────────────────────────────────────────────────────────────
    base_url      = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers       = shopify_headers(store_config["access_token"])
    openai_client = OpenAI(api_key=store_config["openai_key"])

    # ── Produits (statut : depuis la config, sinon demande) ───────────────────
    status_cfg = (cfg.get("product_status") or "").strip().lower()
    if status_cfg in ("active", "draft"):
        product_status = status_cfg
    elif status_cfg == "all":
        product_status = None
    else:
        product_status = ask_product_status()   # non défini en config → demande dans le terminal

    print("\n[1/3] Récupération des produits et images...")
    products = fetch_all_products_with_images(base_url, headers, status=product_status)
    targets  = [p for p in products if p.get("images")]

    if not targets:
        log("Aucun produit avec image — arrêt.", "error", also_print=True)
        return

    # ── Résumé + confirmation ─────────────────────────────────────────────────
    print("\n" + "─" * 50)
    print("  ANALYSE — Fond Studio")
    print("─" * 50)
    print(f"  Produits avec image : {len(targets)}")
    print(f"  Statut traité       : {product_status or 'tous'}")
    print(f"  Couleur du fond     : {color!r}")
    print(f"  Taille / format     : {size} / {output_format}")
    print("─" * 50)
    print("\n  Règles :")
    print("  • 1 image régénérée par produit (la 1ère photo, mise sur fond uni)")
    print("  • La nouvelle image devient la 1ère — l'ancienne 1ère est conservée juste après")
    print("─" * 50)

    total_cost, per_image = _estimate_cost(len(targets), size)
    print("\n  ESTIMATION COÛT OPENAI (gpt-image-1, qualité normale)")
    print("─" * 50)
    print(f"  Images à générer    : {len(targets)}")
    print(f"  Coût par image (~)  : ${per_image:.3f} USD")
    print(f"  Coût total estimé   : ~${total_cost:.2f} USD")
    print("  (indicatif — voir openai.com/api/pricing)")
    print("─" * 50)
    log(f"Estimation Fond Studio — {len(targets)} images | ~${total_cost:.2f} USD ({size})")

    print("\n" + "=" * 60)
    answer = input("Lancer la régénération des images ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Fond Studio annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    # ── Injection (avec reprise) ──────────────────────────────────────────────
    print("\n[2/3] Régénération et injection en cours...")
    last_index, completed_handles = load_progress(store_path)
    if last_index >= 0:
        print(f"[REPRISE] Checkpoint détecté — reprise depuis le produit {last_index + 1}")

    ok_count      = 0
    fail_count    = 0
    injection_log = []

    for idx, product in enumerate(tqdm(targets, desc="Images régénérées")):
        handle     = product.get("handle", "")
        product_id = product.get("id")

        if handle in completed_handles:
            log(f"Skip (déjà traité) : {handle}")
            continue

        try:
            first_url  = product["images"][0].get("src", "")
            alt        = product.get("title", "")
            img_bytes  = download_image(first_url)
            new_png    = regenerate_on_background(img_bytes, first_url, color, openai_client, size, output_format, quality)
            image      = add_first_image(product_id, new_png, alt, base_url, headers)

            ok_count += 1
            completed_handles.append(handle)
            save_progress(store_path, idx, completed_handles)
            injection_log.append({
                "handle": handle, "product_id": product_id,
                "new_image_id": image.get("id", ""), "statut": "OK", "erreur": "",
            })
            print(f"  ✓ {handle}")

        except Exception as e:
            fail_count += 1
            log(f"Fond Studio ÉCHEC — {handle} | {e}", "error", also_print=True)
            injection_log.append({
                "handle": handle, "product_id": product_id,
                "new_image_id": "", "statut": "ERREUR", "erreur": str(e),
            })
            continue

    # ── Rapport + résumé ──────────────────────────────────────────────────────
    print("\n[3/3] Génération du rapport...")
    if injection_log:
        generate_injection_report(injection_log, store_path)

    log(f"Terminé Fond Studio | OK: {ok_count} | Erreurs: {fail_count}")
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique      : {store_name}")
    print(f"  Images OK     : {ok_count}")
    print(f"  Images KO     : {fail_count}")
    print(f"  Logs          : {LOG_FILE}")
    print("=" * 60)

    if fail_count == 0:
        clear_progress(store_path)
        log("Progression effacée — tous les produits Fond Studio traités.")
