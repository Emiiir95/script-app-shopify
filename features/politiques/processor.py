#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
processor.py — Chargement et remplissage des templates de politiques.

Lit les fichiers HTML dans stores/{boutique}/politiques/,
remplace les {{placeholders}} par les vraies valeurs de config.json,
et retourne le HTML final prêt à injecter dans Shopify.

Placeholders disponibles dans les templates :
  {{store_name}}             — Nom de la boutique
  {{company_name}}           — Nom de l'entreprise
  {{email}}                  — Email de contact
  {{phone}}                  — Téléphone
  {{address}}                — Adresse postale complète
  {{siret}}                  — Numéro SIRET
  {{processing_time}}        — Délai de traitement commande (ex: "2-3 jours ouvrés")
  {{shipping_delay}}         — Délai d'acheminement (ex: "5-7 jours ouvrés")
  {{website_url}}            — URL publique du site (ex: https://www.boutique.com)

  — Liens directs vers les pages de politiques Shopify —
  {{url_remboursement}}             — /policies/refund-policy
  {{url_confidentialite}}    — /policies/privacy-policy
  {{url_conditions_service}} — /policies/terms-of-service
  {{url_expedition}}         — /policies/shipping-policy
  {{url_coordonnees}}        — /policies/contact-information
  {{url_conditions_vente}}   — /policies/terms-of-sale
  {{url_mentions_legales}}   — /policies/legal-notice
  {{url_page_retour}}        — /pages/return-policy (page custom)
  {{date_injection}}         — Date du jour au moment de l'injection (DD/MM/YYYY)
"""

import os
from datetime import date
from utils.logger import log


def load_template(store_path, filename):
    """
    Charge un fichier template HTML depuis stores/{boutique}/politiques/.

    Args:
        store_path : chemin absolu vers stores/{boutique}/
        filename   : nom du fichier (ex: "politique_retour.html")

    Returns:
        str : contenu du fichier, ou None si le fichier n'existe pas
    """
    path = os.path.join(store_path, "politiques", filename)
    if not os.path.exists(path):
        log(f"Template absent : {path}", "warning")
        return None
    with open(path, encoding="utf-8") as f:
        return f.read()


def fill_placeholders(content, store_name, legal_info):
    """
    Remplace tous les {{placeholders}} par les vraies valeurs.

    Args:
        content    : contenu HTML du template
        store_name : nom de la boutique (depuis config.json racine)
        legal_info : dict depuis config.json > legal_info

    Returns:
        str : HTML avec tous les placeholders remplacés
    """
    website_url = legal_info.get("website_url", "").rstrip("/")

    replacements = {
        "{{store_name}}":              store_name,
        "{{company_name}}":            legal_info.get("company_name", ""),
        "{{email}}":                   legal_info.get("email", ""),
        "{{phone}}":                   legal_info.get("phone", ""),
        "{{address}}":                 legal_info.get("address", ""),
        "{{siret}}":                   legal_info.get("siret", ""),
        "{{processing_time}}":         legal_info.get("processing_time", ""),
        "{{shipping_delay}}":          legal_info.get("shipping_delay", ""),
        "{{website_url}}":             website_url,
        "{{url_remboursement}}":              f"{website_url}/policies/refund-policy",
        "{{url_confidentialite}}":     f"{website_url}/policies/privacy-policy",
        "{{url_conditions_service}}":  f"{website_url}/policies/terms-of-service",
        "{{url_expedition}}":          f"{website_url}/policies/shipping-policy",
        "{{url_coordonnees}}":         f"{website_url}/policies/contact-information",
        "{{url_conditions_vente}}":    f"{website_url}/policies/terms-of-sale",
        "{{url_mentions_legales}}":    f"{website_url}/policies/legal-notice",
        "{{url_page_retour}}":         f"{website_url}/pages/return-policy",
        "{{date_injection}}":          date.today().strftime("%d/%m/%Y"),
    }

    result = content
    for placeholder, value in replacements.items():
        result = result.replace(placeholder, str(value))

    # Détecte les placeholders non remplacés et les log
    import re
    remaining = re.findall(r"\{\{[^}]+\}\}", result)
    if remaining:
        for r in set(remaining):
            log(f"Placeholder non remplacé dans le template : {r}", "warning", also_print=True)

    return result


def list_missing_templates(store_path, required_files):
    """
    Retourne la liste des fichiers templates absents.

    Args:
        store_path     : chemin absolu vers stores/{boutique}/
        required_files : liste de noms de fichiers à vérifier

    Returns:
        list : noms de fichiers manquants
    """
    missing = []
    politiques_dir = os.path.join(store_path, "politiques")
    for filename in required_files:
        if not os.path.exists(os.path.join(politiques_dir, filename)):
            missing.append(filename)
    return missing
