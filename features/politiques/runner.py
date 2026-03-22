#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
runner.py — Orchestration feature Politiques.

Flow :
  1. Vérifie que legal_info est présent dans config.json
  2. Liste les templates présents dans stores/{boutique}/politiques/
  3. Résumé terminal : quelles politiques seront injectées / skippées
  4. Confirmation utilisateur
  5. Remplit les placeholders dans chaque template
  6. Injecte les politiques intégrées Shopify via GraphQL (shopPoliciesUpdate)
  7. Crée/met à jour la page custom "Politique De Retour" via REST
  8. Rapport CSV post-injection horodaté

Aucun appel OpenAI — remplacement de placeholders uniquement.
"""

import sys

from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
from features.politiques.processor import (
    load_template,
    fill_placeholders,
    list_missing_templates,
)
from features.politiques.injector import (
    POLICY_DEFINITIONS,
    PAGE_DEFINITION,
    fetch_existing_policies,
    update_shopify_policies,
    fetch_page_by_handle,
    create_page,
    update_page,
    generate_injection_report,
)
from utils.logger import log, LOG_FILE


def run(store_config, store_path):
    """
    Point d'entrée de la feature Politiques.

    Args:
        store_config : dict { name, store_url, access_token, ... }
        store_path   : chemin absolu vers stores/{boutique}/
    """
    store_name = store_config.get("name", "boutique")

    log("=" * 60)
    log(f"Démarrage feature Politiques — boutique : {store_name}")
    print("=" * 60)
    print(f"  Politiques — {store_name}")
    print(f"  Logs : {LOG_FILE}")
    print("=" * 60)

    # ── Vérification legal_info ────────────────────────────────────────────────
    legal_info = store_config.get("legal_info", {})
    if not legal_info:
        print("\n[ERREUR] La section 'legal_info' est absente de config.json")
        print("→ Ajoutez les informations légales dans config.json (voir CONFIG.md)")
        log("Politiques — legal_info manquant dans config.json", "error", also_print=False)
        return

    required_fields = ["email", "phone", "address", "company_name", "siret",
                       "processing_time", "shipping_delay", "website_url"]
    missing_fields = [f for f in required_fields if not legal_info.get(f)]
    if missing_fields:
        print(f"\n[AVERTISSEMENT] Champs manquants dans legal_info : {', '.join(missing_fields)}")
        print("→ Les placeholders correspondants resteront vides dans les politiques.")

    # ── Connexion Shopify ──────────────────────────────────────────────────────
    base_url = shopify_base_url(store_config["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(store_config["access_token"])

    # ── Analyse des templates disponibles ─────────────────────────────────────
    all_templates    = [p["template"] for p in POLICY_DEFINITIONS] + [PAGE_DEFINITION["template"]]
    missing_templates = list_missing_templates(store_path, all_templates)

    has_template_policies = [p for p in POLICY_DEFINITIONS if p["template"] not in missing_templates]
    no_template_policies  = [p for p in POLICY_DEFINITIONS if p["template"] in missing_templates]
    page_has_template     = PAGE_DEFINITION["template"] not in missing_templates

    if not has_template_policies and not page_has_template:
        print("\n[ERREUR] Aucun template trouvé dans stores/{boutique}/politiques/")
        print("→ Créez vos fichiers HTML depuis le dossier stores/_template/politiques/")
        return

    # ── Vérification état actuel Shopify ──────────────────────────────────────
    print("\n  Vérification de l'état actuel sur Shopify...")
    existing_policies = fetch_existing_policies(base_url, headers)
    existing_page     = fetch_page_by_handle(PAGE_DEFINITION["handle"], base_url, headers)

    # Mapping handle REST → type GraphQL
    HANDLE_TO_TYPE = {
        "refund-policy":       "REFUND_POLICY",
        "privacy-policy":      "PRIVACY_POLICY",
        "terms-of-service":    "TERMS_OF_SERVICE",
        "shipping-policy":     "SHIPPING_POLICY",
        "contact-information": "CONTACT_INFORMATION",
        "terms-of-sale":       "TERMS_OF_SALE",
        "legal-notice":        "LEGAL_NOTICE",
    }
    TYPE_TO_HANDLE = {v: k for k, v in HANDLE_TO_TYPE.items()}

    # Sépare : à injecter (vide sur Shopify) vs déjà en place (a du contenu)
    to_inject  = [p for p in has_template_policies
                  if not existing_policies.get(TYPE_TO_HANDLE.get(p["type"], ""), False)]
    already_ok = [p for p in has_template_policies
                  if existing_policies.get(TYPE_TO_HANDLE.get(p["type"], ""), False)]

    page_to_create = page_has_template and not existing_page
    page_to_update = page_has_template and existing_page

    print("\n" + "─" * 50)
    print("  ANALYSE — Politiques")
    print("─" * 50)

    if to_inject or page_to_create:
        print("\n  À injecter (absentes sur Shopify) :")
        for p in to_inject:
            print(f"    → {p['label']}")
        if page_to_create:
            print(f"    → {PAGE_DEFINITION['label']} (sera créée)")

    if already_ok or page_to_update:
        print("\n  Déjà en place (contenu existant sur Shopify) :")
        for p in already_ok:
            print(f"    ✓ {p['label']}")
        if page_to_update:
            print(f"    ✓ {PAGE_DEFINITION['label']} (existe déjà)")

    if no_template_policies or not page_has_template:
        print("\n  Skippées (template absent dans stores/{boutique}/politiques/) :")
        for p in no_template_policies:
            print(f"    ✗ {p['label']}  → {p['template']}")
        if not page_has_template:
            print(f"    ✗ {PAGE_DEFINITION['label']}  → {PAGE_DEFINITION['template']}")

    if not to_inject and not page_to_create:
        print("\n  Toutes les politiques sont déjà en place sur Shopify.")
        update_answer = input("  Voulez-vous quand même tout mettre à jour ? (yes/no) : ").strip().lower()
        if update_answer not in ("yes", "y", "o", "oui"):
            print("[ANNULÉ] Aucune modification effectuée.")
            return
        # Forcer l'injection de tout ce qui a un template
        to_inject    = has_template_policies
        page_to_create = False
        page_to_update = page_has_template

    print("\n  Infos légales chargées depuis config.json :")
    print(f"    Société    : {legal_info.get('company_name', '—')}")
    print(f"    Email      : {legal_info.get('email', '—')}")
    print(f"    Téléphone  : {legal_info.get('phone', '—')}")
    print(f"    SIRET      : {legal_info.get('siret', '—')}")
    print(f"    Site web   : {legal_info.get('website_url', '—')}")
    print("─" * 50)

    print("\n" + "=" * 60)
    answer = input("Lancer l'injection des politiques ? (yes/no) : ").strip().lower()
    if answer not in ("yes", "y", "o", "oui"):
        log("Politiques — annulé par l'utilisateur.")
        print("[ANNULÉ] Aucune modification effectuée.")
        return

    injection_log = []

    # ── Injection politiques intégrées Shopify ────────────────────────────────
    if to_inject:
        print("\n[1/2] Injection des politiques Shopify (Settings > Politiques)...")
        policies_data = []
        for p in to_inject:
            content = load_template(store_path, p["template"])
            if not content:
                continue
            body = fill_placeholders(content, store_name, legal_info)
            policies_data.append({
                "type":  p["type"],
                "body":  body,
                "label": p["label"],
            })

        if policies_data:
            results = update_shopify_policies(policies_data, base_url, headers)
            for r in results:
                injection_log.append({
                    "label":  r["label"],
                    "type":   r["type"],
                    "cible":  "Shopify Settings",
                    "statut": r["statut"],
                    "url":    r["url"],
                    "erreur": r["erreur"],
                })
                status_icon = "OK" if r["statut"] == "OK" else "ERREUR"
                print(f"  [{status_icon}] {r['label']}")
    else:
        print("\n[1/2] Politiques Shopify — rien à injecter.")

    # ── Injection page custom ──────────────────────────────────────────────────
    if page_to_create or page_to_update:
        print("\n[2/2] Injection de la page custom (Online Store > Pages)...")
        content = load_template(store_path, PAGE_DEFINITION["template"])
        if content:
            body   = fill_placeholders(content, store_name, legal_info)
            handle = PAGE_DEFINITION["handle"]
            title  = PAGE_DEFINITION["title"]

            if page_to_update:
                result = update_page(existing_page["id"], title, body, base_url, headers)
                action = "MISE À JOUR"
            else:
                result = create_page(title, handle, body, base_url, headers)
                action = "CRÉÉE"

            statut = "OK" if result else "ERREUR"
            injection_log.append({
                "label":  PAGE_DEFINITION["label"],
                "type":   f"PAGE ({action})",
                "cible":  f"/pages/{handle}",
                "statut": statut,
                "url":    f"{legal_info.get('website_url', '')}/pages/{handle}",
                "erreur": "" if result else "Échec création/mise à jour",
            })
            print(f"  [{statut}] {PAGE_DEFINITION['label']} ({action})")
    else:
        print("\n[2/2] Page custom — rien à injecter.")

    # ── Rapport ────────────────────────────────────────────────────────────────
    print("\n[3/3] Génération du rapport...")
    generate_injection_report(injection_log, store_path)

    ok_count  = sum(1 for e in injection_log if e["statut"] == "OK")
    err_count = sum(1 for e in injection_log if e["statut"] == "ERREUR")

    log(f"Terminé Politiques | OK: {ok_count} | Erreurs: {err_count}")
    print("\n[FIN] Résumé final")
    print("=" * 60)
    print(f"  Boutique     : {store_name}")
    print(f"  Politiques OK : {ok_count}")
    print(f"  Erreurs       : {err_count}")
    print(f"  Logs          : {LOG_FILE}")
    print("=" * 60)
