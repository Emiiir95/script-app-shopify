"""
runner.py — Orchestration du transfert entre deux boutiques Shopify.

Flow :
  1. Le store source est déjà sélectionné dans main.py
  2. L'utilisateur choisit le store destination
  3. Export complet du store source (definitions, metaobjects, produits, metafields)
  4. Résumé + confirmation utilisateur
  5. Import complet vers le store destination (avec remap GID)
  6. Résumé final
"""

import os
import sys
import json

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from features.transfert.exporter import export_all
from features.transfert.importer import import_all
from utils.logger import log, LOG_FILE


STORES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "stores")


def _select_destination(source_store_url):
    """Liste les stores disponibles et demande à l'utilisateur de choisir la destination."""
    dest_stores = []

    for entry in sorted(os.listdir(STORES_DIR)):
        if entry.startswith("_"):
            continue
        store_path = os.path.join(STORES_DIR, entry)
        config_path = os.path.join(store_path, "config.json")
        if os.path.isdir(store_path) and os.path.exists(config_path):
            with open(config_path, encoding="utf-8") as f:
                cfg = json.load(f)
            # Exclure le store source
            if cfg.get("store_url") != source_store_url:
                dest_stores.append((entry, store_path, cfg))

    if not dest_stores:
        print("\n[ERREUR] Aucune autre boutique disponible comme destination.")
        print("→ Créez un dossier dans stores/ avec un config.json pour le nouveau store.")
        return None

    print("\n  Boutiques destination disponibles :\n")
    for i, (folder, _, cfg) in enumerate(dest_stores, start=1):
        print(f"  {i}. {cfg.get('name', folder)}  ({cfg.get('store_url', '')})")

    choice = input("\nChoisissez la destination : ").strip()
    try:
        idx = int(choice) - 1
        assert 0 <= idx < len(dest_stores)
    except (ValueError, AssertionError):
        print("Choix invalide.")
        return None

    return dest_stores[idx][2]


def run(store_config, store_path):
    """
    Point d'entrée de la feature Transfert.

    store_config : dict { name, store_url, access_token, openai_key }
    store_path   : chemin absolu vers stores/{boutique}/ (source)
    """
    store_name = store_config.get("name", "boutique")
    source_url = store_config["store_url"]

    log("=" * 60)
    log(f"Démarrage feature Transfert — source : {store_name}")
    print("=" * 60)
    print(f"  Transfert — Source : {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    # ── Sélection destination ─────────────────────────────────────────────────
    dest_config = _select_destination(source_url)
    if not dest_config:
        return

    dest_name = dest_config.get("name", "destination")

    print(f"\n  Source      : {store_name}  ({source_url})")
    print(f"  Destination : {dest_name}  ({dest_config['store_url']})")
    print("\n  ⚠ Les produits, metaobjects, fichiers et metafields seront CRÉÉS sur la destination.")

    answer = input("\nConfirmer le transfert ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "oui", "o"):
        print("\n[ANNULÉ]")
        return

    # ── Connexion aux deux stores ─────────────────────────────────────────────
    source_base = shopify_base_url(source_url, SHOPIFY_API_VERSION)
    source_hdrs = shopify_headers(store_config["access_token"])
    dest_base   = shopify_base_url(dest_config["store_url"], SHOPIFY_API_VERSION)
    dest_hdrs   = shopify_headers(dest_config["access_token"])

    # ── Export ────────────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("  EXPORT — Lecture du store source")
    print("─" * 60)

    export_data = export_all(source_base, source_hdrs)

    # ── Résumé export ─────────────────────────────────────────────────────────
    n_defs      = len(export_data["metaobject_definitions"])
    n_mos       = sum(len(v) for v in export_data["metaobjects"].values())
    n_mf_defs   = len(export_data["metafield_definitions"])
    n_products  = len(export_data["products"])
    n_mfs       = sum(len(v) for v in export_data["product_metafields"].values())
    n_files     = len(export_data.get("file_urls", {}))

    print(f"\n  Résumé export :")
    print(f"  • Metaobject definitions : {n_defs}")
    print(f"  • Metaobjects            : {n_mos}")
    print(f"  • Metafield definitions  : {n_mf_defs}")
    print(f"  • Produits               : {n_products}")
    print(f"  • Metafields produit     : {n_mfs}")
    print(f"  • Fichiers (images)      : {n_files}")

    if n_products == 0:
        print("\n[INFO] Aucun produit à transférer — arrêt.")
        return

    answer = input("\nInjecter dans la destination ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "oui", "o"):
        print("\n[ANNULÉ]")
        return

    # ── Import ────────────────────────────────────────────────────────────────
    print("\n" + "─" * 60)
    print("  IMPORT — Injection vers la destination")
    print("─" * 60)

    remaps = import_all(export_data, dest_base, dest_hdrs)

    # ── Résumé final ──────────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Transfert terminé !")
    print(f"  • Definitions créées/existantes : {len(remaps['mo_def_remap'])}")
    print(f"  • Fichiers créés                : {len(remaps.get('file_remap', {}))}")
    print(f"  • Metaobjects créés             : {len(remaps['metaobject_remap'])}")
    print(f"  • Produits créés                : {len(remaps['product_remap'])}")
    print("=" * 60)

    log(f"Transfert terminé — {len(remaps['product_remap'])} produit(s), "
        f"{len(remaps['metaobject_remap'])} metaobject(s), "
        f"{len(remaps.get('file_remap', {}))} fichier(s)")
