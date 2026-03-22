import csv
import os
import time
from datetime import datetime

from tqdm import tqdm

from shopify.metaobjects import create_metaobject
from shopify.products import set_product_metafield
from utils.logger import log

def generate_csv_preview(products_data, store_path):
    """Génère le CSV preview dans le dossier de la boutique (store_path/reviews_preview.csv)."""
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path = os.path.join(store_path, "rapports", "reviews_preview.csv")
    fieldnames = ["handle", "rating_global", "review_count"]
    for i in range(1, 9):
        fieldnames += [f"review{i}_title", f"review{i}_text", f"review{i}_author", f"review{i}_rating"]

    with open(csv_path, "w", newline="", encoding="utf-8") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for pd in products_data:
            row = {
                "handle":        pd["handle"],
                "rating_global": pd["rating"],
                "review_count":  pd["count"],
            }
            for i, review in enumerate(pd["reviews"], start=1):
                row[f"review{i}_title"]  = review.get("titre", "")
                row[f"review{i}_text"]   = review.get("texte", "")
                row[f"review{i}_author"] = review.get("nom_auteur", "")
                row[f"review{i}_rating"] = review.get("note", 5)
            writer.writerow(row)

    log(f"CSV preview généré : {csv_path}")
    print(f"\n[CSV] Preview généré : {csv_path}")


def generate_injection_report(injection_log, store_path):
    """
    Génère le rapport CSV post-injection Reviews : tout ce qui a été envoyé dans Shopify.

    Colonnes :
        date_heure, handle, note_globale, nb_avis_injectes,
        avis1_titre … avis8_titre, avis1_texte … avis8_texte,
        avis1_auteur … avis8_auteur, avis1_note … avis8_note,
        statut, erreur

    Args:
        injection_log : liste de dicts { product, entry, statut, erreur }
        store_path    : chemin absolu vers le dossier de la boutique

    Returns:
        str : chemin absolu du rapport généré
    """
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    os.makedirs(os.path.join(store_path, "rapports"), exist_ok=True)
    csv_path  = os.path.join(store_path, "rapports", f"reviews_rapport_{timestamp}.csv")

    fieldnames = ["date_heure", "handle", "note_globale", "nb_avis_injectes"]
    for i in range(1, 9):
        fieldnames += [f"avis{i}_titre", f"avis{i}_texte", f"avis{i}_auteur", f"avis{i}_note"]
    fieldnames += ["statut", "erreur"]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for entry in injection_log:
            product  = entry["product"]
            data     = entry["entry"]
            reviews  = data.get("reviews", [])
            row = {
                "date_heure":        now_str,
                "handle":            product.get("handle", ""),
                "note_globale":      data.get("note_globale", ""),
                "nb_avis_injectes":  len(reviews),
                "statut":            entry["statut"],
                "erreur":            entry.get("erreur", ""),
            }
            for i in range(1, 9):
                rv = reviews[i - 1] if i <= len(reviews) else {}
                row[f"avis{i}_titre"]  = rv.get("titre", "")
                row[f"avis{i}_texte"]  = rv.get("texte", "")
                row[f"avis{i}_auteur"] = rv.get("nom_auteur", "")
                row[f"avis{i}_note"]   = rv.get("note", "")
            writer.writerow(row)

    log(f"Rapport injection Reviews généré : {csv_path}")
    print(f"\n[RAPPORT] Injection CSV : {csv_path}")
    return csv_path


def inject_product_reviews(product, reviews_data, base_url, headers):
    product_id    = product["id"]
    handle        = product["handle"]
    missing_slots = reviews_data["missing_slots"]
    reviews       = reviews_data["reviews"]

    log(f"Début injection — {handle} | {len(reviews)} avis | slots: {missing_slots}")

    metaobject_gids = []
    for review in tqdm(reviews, desc=f"  Metaobjects {handle}", leave=False):
        gid = create_metaobject(review, base_url, headers)
        metaobject_gids.append(gid)
        log(f"Metaobject créé — {handle} | note: {review.get('note')} | gid: {gid}")
        time.sleep(0.4)

    for slot_idx, gid in zip(missing_slots, metaobject_gids):
        key = f"avis_client_{slot_idx}"
        set_product_metafield(product_id, "custom", key, gid, "metaobject_reference", base_url, headers)
        log(f"Metafield rempli — {handle} | {key} → {gid}")
        time.sleep(0.4)

    set_product_metafield(
        product_id, "custom", "note_globale",
        reviews_data["note_globale"], "single_line_text_field",
        base_url, headers,
    )
    log(f"Note globale remplie — {handle} | {reviews_data['note_globale']}")
