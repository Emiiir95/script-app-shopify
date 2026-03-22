#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
injector.py — Injection des politiques dans Shopify.

Deux cibles distinctes :
  1. Politiques intégrées Shopify (Settings > Politiques)
     → GraphQL mutation shopPoliciesUpdate
     → Types : REFUND_POLICY, PRIVACY_POLICY, TERMS_OF_SERVICE,
               SHIPPING_POLICY, CONTACT_INFORMATION, TERMS_OF_SALE, LEGAL_NOTICE

  2. Pages Shopify personnalisées (Online Store > Pages)
     → REST /pages.json
     → Page "Politique De Retour" à l'URL /pages/return-policy

Fonctions publiques :
  - update_shopify_policies   : met à jour les politiques via GraphQL
  - fetch_page_by_handle      : cherche une page par son handle (REST)
  - create_page               : crée une nouvelle page (REST)
  - update_page               : met à jour une page existante (REST)
  - generate_injection_report : CSV post-injection horodaté
"""

import csv
import os
from datetime import datetime

from shopify.client import graphql_request, shopify_get, shopify_post, shopify_put
from utils.logger import log


# ── Politiques intégrées Shopify ───────────────────────────────────────────────

_MUTATION = """
mutation shopPoliciesUpdate($policies: [ShopPolicyInput!]!) {
  shopPoliciesUpdate(policies: $policies) {
    shopPolicies {
      type
      url
    }
    userErrors {
      field
      message
    }
  }
}
"""

# Correspondance clé interne → type GraphQL + libellé affiché
POLICY_DEFINITIONS = [
    {
        "key":      "politique_remboursement",
        "type":     "REFUND_POLICY",
        "label":    "Politique de remboursement",
        "template": "politique_remboursement.html",
    },
    {
        "key":      "politique_confidentialite",
        "type":     "PRIVACY_POLICY",
        "label":    "Politique de confidentialité",
        "template": "politique_confidentialite.html",
    },
    {
        "key":      "conditions_service",
        "type":     "TERMS_OF_SERVICE",
        "label":    "Conditions de service",
        "template": "conditions_service.html",
    },
    {
        "key":      "politique_expedition",
        "type":     "SHIPPING_POLICY",
        "label":    "Politique d'expédition",
        "template": "politique_expedition.html",
    },
    {
        "key":      "coordonnees",
        "type":     "CONTACT_INFORMATION",
        "label":    "Coordonnées",
        "template": "coordonnees.html",
    },
    {
        "key":      "conditions_vente",
        "type":     "TERMS_OF_SALE",
        "label":    "Conditions de vente",
        "template": "conditions_vente.html",
    },
    {
        "key":      "mentions_legales",
        "type":     "LEGAL_NOTICE",
        "label":    "Mentions légales",
        "template": "mentions_legales.html",
    },
]

# Page personnalisée (Online Store > Pages)
PAGE_DEFINITION = {
    "key":      "page_retour",
    "title":    "Politique De Retour",
    "handle":   "return-policy",
    "label":    "Page Politique De Retour (/pages/return-policy)",
    "template": "page-politique_retour.html",
}


def fetch_existing_policies(base_url, headers):
    """
    Récupère les politiques actuellement en place sur Shopify via REST.

    Returns:
        dict : { handle: bool } — True si la politique a déjà du contenu
               Ex: {"refund-policy": True, "privacy-policy": False, ...}
    """
    try:
        data = shopify_get(f"{base_url}/policies.json", headers)
        policies = data.get("policies", [])
        return {p["handle"]: bool(p.get("body", "").strip()) for p in policies}
    except Exception as e:
        log(f"Impossible de récupérer les politiques existantes : {e}", "warning")
        return {}


def update_shopify_policies(policies_data, base_url, headers):
    """
    Met à jour les politiques intégrées Shopify via GraphQL shopPoliciesUpdate.

    Args:
        policies_data : liste de dicts {"type": str, "body": str, "label": str}
        base_url      : URL de base REST Shopify
        headers       : dict headers Shopify

    Returns:
        list de dicts {"label", "type", "statut", "url", "erreur"}
    """
    results = []

    # Envoie tout en un seul appel GraphQL
    files_input = [{"type": p["type"], "body": p["body"]} for p in policies_data]

    try:
        data        = graphql_request(base_url, headers, _MUTATION, {"policies": files_input})
        payload     = data["data"]["shopPoliciesUpdate"]
        user_errors = payload.get("userErrors", [])

        if user_errors:
            # Erreurs partielles — on mappe par type si possible
            error_types = {e.get("field", ""): e.get("message", "") for e in user_errors}
            for p in policies_data:
                err = error_types.get(p["type"], "")
                results.append({
                    "label":  p["label"],
                    "type":   p["type"],
                    "statut": "ERREUR" if err else "OK",
                    "url":    "",
                    "erreur": err,
                })
        else:
            url_map = {sp["type"]: sp.get("url", "") for sp in payload.get("shopPolicies", [])}
            for p in policies_data:
                results.append({
                    "label":  p["label"],
                    "type":   p["type"],
                    "statut": "OK",
                    "url":    url_map.get(p["type"], ""),
                    "erreur": "",
                })
            log(f"Politiques Shopify mises à jour : {[p['type'] for p in policies_data]}")

    except Exception as e:
        log(f"Erreur shopPoliciesUpdate : {e}", "error", also_print=True)
        for p in policies_data:
            results.append({
                "label":  p["label"],
                "type":   p["type"],
                "statut": "ERREUR",
                "url":    "",
                "erreur": str(e),
            })

    return results


def fetch_page_by_handle(handle, base_url, headers):
    """
    Cherche une page Shopify par son handle.

    Returns:
        dict ou None
    """
    url = f"{base_url}/pages.json"
    try:
        data  = shopify_get(url, headers, params={"handle": handle, "fields": "id,handle,title"})
        pages = data.get("pages", [])
        for page in pages:
            if page.get("handle") == handle:
                return page
        return None
    except Exception as e:
        if "403" in str(e):
            log("Pages Shopify inaccessibles (403) — scope 'read_content' manquant sur le token.", "warning", also_print=True)
        else:
            log(f"Erreur fetch page '{handle}' : {e}", "warning", also_print=True)
        return None


def create_page(title, handle, body_html, base_url, headers):
    """
    Crée une nouvelle page Shopify.

    Returns:
        dict : page créée ou None si erreur
    """
    payload = {
        "page": {
            "title":     title,
            "handle":    handle,
            "body_html": body_html,
            "published": True,
        }
    }
    try:
        data   = shopify_post(f"{base_url}/pages.json", headers, payload)
        result = data.get("page", {})
        log(f"Page CRÉÉE : {title} (handle: {handle}, id: {result.get('id')})")
        return result
    except Exception as e:
        log(f"Erreur création page '{title}' : {e}", "error", also_print=True)
        return None


def update_page(page_id, title, body_html, base_url, headers):
    """
    Met à jour une page Shopify existante.

    Returns:
        dict : page mise à jour ou None si erreur
    """
    payload = {
        "page": {
            "id":        page_id,
            "title":     title,
            "body_html": body_html,
        }
    }
    try:
        data   = shopify_put(f"{base_url}/pages/{page_id}.json", headers, payload)
        result = data.get("page", {})
        log(f"Page MISE À JOUR : {title} (id: {page_id})")
        return result
    except Exception as e:
        log(f"Erreur update page '{title}' : {e}", "error", also_print=True)
        return None


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-injection des politiques.

    Colonnes : date_heure, label, type, cible, statut, url, erreur

    Returns:
        str : chemin absolu du rapport
    """
    timestamp  = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path   = os.path.join(store_path, "rapports", f"politiques_rapport_{timestamp}.csv")
    fieldnames = ["date_heure", "label", "type", "cible", "statut", "url", "erreur"]
    now_str    = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            writer.writerow({
                "date_heure": now_str,
                "label":      entry.get("label", ""),
                "type":       entry.get("type", ""),
                "cible":      entry.get("cible", ""),
                "statut":     entry.get("statut", ""),
                "url":        entry.get("url", ""),
                "erreur":     entry.get("erreur", ""),
            })

    log(f"Rapport politiques généré : {csv_path}")
    print(f"\n[RAPPORT] CSV : {csv_path}")
    return csv_path
