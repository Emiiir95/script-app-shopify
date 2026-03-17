#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
main.py — Point d'entrée de Shopify Automation.

Flow :
  1. Sélection de la boutique (dossier dans stores/)
  2. Sélection de la feature à lancer
  3. Délégation au module runner de la feature avec (store_config, store_path)

Lancement :
  cd /Users/.../script
  python main.py
"""

import sys
import os
import json
import importlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

STORES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "stores")
ENV_FILE   = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")

# Features disponibles : clé = numéro, valeur = (label, module_path ou None si pas prêt)
FEATURES = {
    "1": ("Reviews — Génération et injection d'avis clients", "features.reviews.runner"),
    "2": ("Titles  — Réécriture des titres produit",          None),
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


def select_feature():
    print("\n  Features disponibles :\n")
    for key, (label, module_path) in FEATURES.items():
        status = "  [bientôt disponible]" if not module_path else ""
        print(f"  {key}. {label}{status}")

    choice = input("\nChoisissez une feature : ").strip()
    if choice not in FEATURES:
        print("Choix invalide.")
        sys.exit(1)

    label, module_path = FEATURES[choice]
    if not module_path:
        print(f"\n[INFO] '{label.strip()}' n'est pas encore disponible.")
        sys.exit(0)

    return module_path


def main():
    print("=" * 60)
    print("  Shopify Automation")
    print("=" * 60)

    global_env = load_global_env()
    openai_key = global_env.get("OPENAI_API_KEY", "")
    if not openai_key:
        openai_key = input("\nOPENAI_API_KEY (non trouvée dans .env) : ").strip()

    store_config, store_path = select_store()
    store_config["openai_key"] = openai_key

    module_path = select_feature()
    module = importlib.import_module(module_path)
    module.run(store_config, store_path)


if __name__ == "__main__":
    main()
