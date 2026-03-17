import time

from shopify.metaobjects import (
    get_metaobject_definition_id,
    create_metaobject_definition,
    create_metafield_definition,
)
from utils.logger import log


def setup_shopify_structure(base_url, headers):
    print("\n" + "─" * 60)
    print("  SETUP — Vérification de la structure Shopify")
    print("─" * 60)
    answer = input("\nLes metafields et metaobjects sont-ils déjà configurés dans Shopify ? (yes/no) : ").strip().lower()

    if answer in ("yes", "y", "o", "oui"):
        print("[SETUP] Structure existante — aucune création effectuée.")
        log("Setup ignoré — structure déclarée existante par l'utilisateur.")
        return

    print("\n[SETUP] Création de la structure en cours...")
    log("Début setup structure Shopify")

    print("  → Création du metaobject definition 'avis_client'...")
    try:
        mo_def_id = get_metaobject_definition_id(base_url, headers)
        if mo_def_id:
            print(f"  ✓ Metaobject definition 'avis_client' déjà existant (id: {mo_def_id})")
            log(f"Metaobject definition 'avis_client' déjà existant : {mo_def_id}")
        else:
            mo_def_id = create_metaobject_definition(base_url, headers)
            print(f"  ✓ Metaobject definition 'avis_client' créé (id: {mo_def_id})")
    except Exception as e:
        print(f"  ✗ Erreur metaobject definition : {e}")
        log(f"Erreur création metaobject definition : {e}", "error")
        mo_def_id = None

    print("  → Création metafield 'note_globale_du_produit'...")
    try:
        create_metafield_definition(
            base_url, headers,
            name="Note globale du produit",
            key="note_globale_du_produit",
            field_type="single_line_text_field",
        )
        print("  ✓ note_globale_du_produit")
    except Exception as e:
        print(f"  ✗ note_globale_du_produit : {e}")
        log(f"Erreur note_globale_du_produit : {e}", "error")

    for i in range(1, 9):
        key = f"avis_clients_{i}"
        print(f"  → Création metafield '{key}'...")
        try:
            create_metafield_definition(
                base_url, headers,
                name=f"Avis clients {i}",
                key=key,
                field_type="metaobject_reference",
                mo_def_id=mo_def_id,
            )
            print(f"  ✓ {key}")
        except Exception as e:
            print(f"  ✗ {key} : {e}")
            log(f"Erreur {key} : {e}", "error")
        time.sleep(0.3)

    print("\n[SETUP] Structure Shopify configurée.")
    log("Setup structure Shopify terminé.")
