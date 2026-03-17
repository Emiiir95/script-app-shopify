import json
import time
import random
import sys

from features.reviews.prompts import build_user_prompt
from utils.logger import log


def generate_reviews_for_product(product_title, n_reviews, openai_client, system_prompt, cost_tracker, max_retries=5):
    user_prompt = build_user_prompt(product_title, n_reviews)

    for attempt in range(max_retries):
        try:
            response = openai_client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=0.85,
                response_format={"type": "json_object"},
            )

            cost_tracker.add(response.usage)
            log(
                f"OpenAI OK — produit: {product_title!r} | "
                f"tokens: {response.usage.prompt_tokens}in/{response.usage.completion_tokens}out | "
                f"coût session: ${cost_tracker.cost_usd:.4f}"
            )

            content   = response.choices[0].message.content
            parsed    = json.loads(content)
            avis_list = parsed.get("avis", [])
            if len(avis_list) < n_reviews:
                avis_list = (avis_list * (n_reviews // len(avis_list) + 1))
            return avis_list[:n_reviews]

        except Exception as e:
            err = str(e)
            if "quota" in err.lower() or "rate" in err.lower() or "429" in err:
                log(f"Quota OpenAI atteint — produit: {product_title!r} (tentative {attempt+1})", "warning", also_print=True)
                print("Rechargez votre crédit OpenAI puis appuyez sur Entrée pour continuer.")
                try:
                    import select
                    rlist, _, _ = select.select([sys.stdin], [], [], 60)
                    if rlist:
                        sys.stdin.readline()
                except Exception:
                    time.sleep(60)
                continue
            else:
                log(f"Erreur OpenAI — produit: {product_title!r} | {err} (tentative {attempt+1}/{max_retries})", "error", also_print=True)
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
                raise Exception(f"Échec génération OpenAI après {max_retries} tentatives : {err}")

    raise Exception("Impossible de générer les avis après plusieurs tentatives.")


def generate_global_note():
    rating = round(random.uniform(4.3, 5.0), 1)
    count  = random.randint(150, 500)
    return f"<strong>{rating}</strong> | {count}+ avis vérifiés", rating, count
