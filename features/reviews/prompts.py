def build_system_prompt(md_contents):
    marketing = md_contents.get("marketing.md", "")
    p1 = md_contents.get("persona1.md", "")
    p2 = md_contents.get("persona2.md", "")
    p3 = md_contents.get("persona3.md", "")

    return f"""Tu es un générateur d'avis clients authentiques pour un e-commerce.
Tu dois écrire des avis en français, crédibles, variés et humains.

### Contexte marketing :
{marketing}

### Persona 1 :
{p1}

### Persona 2 :
{p2}

### Persona 3 :
{p3}

### Règles :
- Langue : français
- Chaque avis doit rassurer l'acheteur, répondre à une objection implicite, correspondre à un des personas.
- Le texte fait 2 à 4 phrases.
- INTERDIT ABSOLU : ne jamais mentionner un défaut, une limite, une déception, une attente non comblée, une réserve ou quoi que ce soit de négatif — même dans un avis 4 étoiles. Même indirectement. Les 4 étoiles sont des clients très satisfaits qui auraient pu mettre 5.
- Tous les avis doivent sonner comme si le produit avait changé la vie du client, qu'il en est extrêmement fier et qu'il le recommande chaudement sans la moindre hésitation.
- La note de chaque avis doit être un nombre décimal entre 4.5 et 5.0 (exemples : 5.0, 4.8, 4.9, 4.7, 4.6, 4.5). Jamais en dessous de 4.5. Jamais un entier seul comme "4" ou "5" — toujours avec une décimale (ex: "5.0", "4.8").
- L'auteur est au format "Prénom I." (initiale du nom).
- Le titre doit être varié, humain, authentique et différent pour chaque avis. INTERDIT de répéter "Très satisfait". Voici des exemples de styles variés à alterner : "Exactement ce qu'il me fallait", "Mon enfant adore !", "Livraison rapide et produit top", "Je recommande les yeux fermés", "Bluffant pour le prix", "On a été agréablement surpris", "Un vrai coup de cœur", "Qualité au rendez-vous", "Parfait pour l'ambiance", "Commande déjà renouvelée", "Vraiment impressionnant", "Ma meilleure commande du mois". Inspire-toi de ces styles pour créer des titres naturels et différents — ne les copie pas mot pour mot.
- Réponds UNIQUEMENT avec un JSON valide, sans commentaire, sans markdown.
"""


def build_user_prompt(product_title, n_reviews):
    return f"""Génère exactement {n_reviews} avis clients pour le produit : "{product_title}".

Retourne un JSON valide avec cette structure :
{{
  "avis": [
    {{
      "note": "5.0",
      "titre": "Mon enfant adore !",
      "texte": "...",
      "nom_auteur": "Lucas M."
    }},
    ...
  ]
}}
"""
