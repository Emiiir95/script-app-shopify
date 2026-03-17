import csv
import os
import time

from tqdm import tqdm

from shopify.metaobjects import create_metaobject
from shopify.products import set_product_metafield
from utils.logger import log

def generate_csv_preview(products_data, store_path):
    """Génère le CSV preview dans le dossier de la boutique (store_path/reviews_preview.csv)."""
    csv_path = os.path.join(store_path, "reviews_preview.csv")
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
