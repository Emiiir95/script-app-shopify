#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — Point d'entrée de Shopify Automation.

Flow :
  1. Sélection de la boutique (dossier dans stores/)
  2. Boucle de session :
       a. Affichage du menu features
       b. Lancement de la feature choisie
       c. Retour au menu (même boutique, même session)
       d. Quitter avec 'q'

Lancement :
  cd /Users/.../script
  python main.py
"""

import sys
import os
import json
import argparse
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STORES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stores")
ENV_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Features disponibles : clé = numéro, valeur = (label, module_path ou None si pas prêt)
FEATURES = {
    "0": ("Setup          — Créer la structure metafields / metaobjects",            "features.setup.runner"),
    "1": ("SEO Boost      — Titres, descriptions, meta title, handle produit, specs","features.seo_boost.runner"),
    "2": ("Fiche Produit  — Phrase, bénéfices, sections feature (images)",           "features.fiche_produit.runner"),
    "3": ("Fond Studio    — Régénère la 1ère image produit sur un fond uni (IA)",     "features.fond_studio.runner"),
    "4": ("Normalisation  — Prix, taxable, stock policy, status produit",            "features.normalisation.runner"),
    "5": ("Reviews        — Génération et injection d'avis clients",                 "features.reviews.runner"),
    "6": ("SEO Images     — Renommage fichiers + alt text via meta title",            "features.seo_images.runner"),
    "7": ("Collections    — Création/mise à jour collections + SEO (depuis config)",  "features.collections.runner"),
    "8": ("Politiques     — Injection politiques légales + page retour",              "features.politiques.runner"),
    "9": ("Transfert      — Copier produits + metaobjects vers autre boutique",       "features.transfert.runner"),
   "10": ("Menus          — Création/mise à jour menus de navigation (depuis config)", "features.menus.runner"),
   "11": ("Rebrand        — Remplacement URL/nom de marque dans descriptions et SEO",  "features.rebrand.runner"),
}


def load_global_env():
    """Charge le .env racine (OpenAI key partagée entre toutes les boutiques)."""
    env = {}
    if not os.path.exists(ENV_FILE):
        return env
    with open(ENV_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("//") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip()
    return env


def list_stores():
    """Retourne les stores valides : dossiers dans stores/ ayant un config.json."""
    stores = []
    if not os.path.isdir(STORES_DIR):
        return stores
    for entry in sorted(os.listdir(STORES_DIR)):
        if entry.startswith("_"):           # ignore _template et fichiers cachés
            continue
        store_path  = os.path.join(STORES_DIR, entry)
        config_path = os.path.join(store_path, "config.json")
        if os.path.isdir(store_path) and os.path.exists(config_path):
            stores.append((entry, store_path, config_path))
    return stores


def select_store():
    stores = list_stores()
    if not stores:
        print("\n[ERREUR] Aucune boutique trouvée dans stores/")
        print("→ Copiez stores/_template/, renommez le dossier, remplissez config.json")
        sys.exit(1)

    print("\n  Boutiques disponibles :\n")
    for i, (folder, _, config_path) in enumerate(stores, start=1):
        with open(config_path, encoding="utf-8") as f:
            cfg = json.load(f)
        print(f"  {i}. {cfg.get('name', folder)}  ({cfg.get('store_url', '')})")

    choice = input("\nChoisissez une boutique : ").strip()
    try:
        idx = int(choice) - 1
        assert 0 <= idx < len(stores)
    except (ValueError, AssertionError):
        print("Choix invalide.")
        sys.exit(1)

    folder, store_path, config_path = stores[idx]
    with open(config_path, encoding="utf-8") as f:
        config = json.load(f)

    print(f"\n  → Boutique : {config.get('name', folder)}")
    return config, store_path


def select_feature(store_name):
    """
    Affiche le menu des features et retourne le module_path choisi.
    Retourne None si l'utilisateur choisit de quitter.
    Boucle sur les choix invalides ou non disponibles.
    """
    while True:
        print("\n" + "─" * 60)
        print(f"  Boutique : {store_name}")
        print("─" * 60)
        print("\n  Features disponibles :\n")
        for key, (label, module_path) in FEATURES.items():
            status = "  [bientôt disponible]" if not module_path else ""
            print(f"  {key}. {label}{status}")
        print("\n  q. Quitter")

        choice = input("\nChoisissez une feature (ou q) : ").strip().lower()

        if choice in ("q", "quit", "exit"):
            return None

        if choice not in FEATURES:
            print("Choix invalide — réessayez.")
            continue

        label, module_path = FEATURES[choice]
        if not module_path:
            print(f"\n[INFO] '{label.strip()}' n'est pas encore disponible.")
            continue

        return module_path


# ── Lancement direct (depuis le backoffice) ────────────────────────────────────

def _feature_id_to_module():
    """Retourne { id_feature: module_path } — ex: 'fond_studio' → 'features.fond_studio.runner'."""
    return {mp.split(".")[1]: mp for (_, mp) in FEATURES.values()}


def find_store_by_folder(folder):
    """Retourne (config, store_path) pour le dossier boutique donné, sinon (None, None)."""
    for name, store_path, config_path in list_stores():
        if name == folder:
            with open(config_path, encoding="utf-8") as f:
                return json.load(f), store_path
    return None, None


def run_direct(store_folder, feature_id):
    """
    Lance une feature directement sur une boutique, sans menu interactif.
    Appelé quand main.py reçoit --store et --feature (bouton « Lancer » du backoffice).
    """
    global_env = load_global_env()
    openai_key = global_env.get("OPENAI_API_KEY", "")

    store_config, store_path = find_store_by_folder(store_folder)
    if not store_config:
        print(f"\n[ERREUR] Boutique introuvable : {store_folder!r}")
        sys.exit(1)
    store_config["openai_key"] = openai_key

    module_path = _feature_id_to_module().get(feature_id)
    if not module_path:
        print(f"\n[ERREUR] Fonctionnalité inconnue : {feature_id!r}")
        sys.exit(1)

    print("=" * 60)
    print(f"  Lancement direct — {feature_id}  →  {store_config.get('name', store_folder)}")
    print("=" * 60)

    module = importlib.import_module(module_path)
    module.run(store_config, store_path)

    input("\n[Terminé] Appuyez sur Entrée pour fermer cette fenêtre...")


def main():
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--store")
    parser.add_argument("--feature")
    cli, _ = parser.parse_known_args()

    # Mode direct : boutique + feature fournies → on lance et on sort
    if cli.store and cli.feature:
        run_direct(cli.store, cli.feature)
        return

    print("=" * 60)
    print("  Shopify Automation")
    print("=" * 60)

    global_env = load_global_env()
    openai_key = global_env.get("OPENAI_API_KEY", "")
    if not openai_key:
        openai_key = input("\nOPENAI_API_KEY (non trouvée dans .env) : ").strip()

    store_config, store_path = select_store()
    store_config["openai_key"] = openai_key
    store_name = store_config.get("name", "boutique")

    # ── Boucle de session ─────────────────────────────────────────────────────
    while True:
        module_path = select_feature(store_name)

        if module_path is None:
            print("\nAu revoir !\n")
            sys.exit(0)

        module = importlib.import_module(module_path)
        module.run(store_config, store_path)


if __name__ == "__main__":
    main()
