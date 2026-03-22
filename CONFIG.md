# CONFIG.md — Guide complet du fichier config.json

Chaque boutique possède son propre `stores/{nom-boutique}/config.json`.
Ce fichier centralise tous les paramètres de la boutique utilisés par les features.

---

## Structure globale

```json
{
  "name":         "Nom affiché dans le terminal",
  "store_url":    "nom-boutique.myshopify.com",
  "access_token": "shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxx",

  "seo_boost":    { ... },
  "fiche_produit": { ... },
  "legal_info":   { ... }
}
```

---

## Champs racine

| Champ | Type | Description |
|---|---|---|
| `name` | string | Nom affiché dans le menu de sélection boutique |
| `store_url` | string | Domaine myshopify (sans `https://`) |
| `access_token` | string | Token d'accès Shopify privé (`shpat_...`) |

**Scopes requis sur le token Shopify :**
```
read_products, write_products
read_metaobjects, write_metaobjects
read_files, write_files
read_publications, write_publications
```

---

## Section `seo_boost`

Utilisée par les features **SEO Boost** et **Collections**.

```json
"seo_boost": {
  "niche_keyword":          "Arbre à Chat",
  "title_style":            "branded",
  "branding_mode":          "theme",
  "branding_position":      "start",
  "brandingNames":          ["Atlas", "Everest", ...],
  "vendor":                 "Le Perchoir Du Chat",
  "word_count":             200,
  "generate_meta_description": true,
  "generate_description":   true,
  "mainCollection":         { "name": "...", "url": "...", "volume": 74000 },
  "collections":            [ ... ]
}
```

### `niche_keyword`
Le mot-clé principal de ta niche. Injecté dans tous les prompts GPT.
- Ex : `"Arbre à Chat"`, `"Veilleuse Bébé"`, `"Coussin Ergonomique"`

### `title_style`
Détermine le format du titre H1 et du handle produit.
| Valeur | Format généré |
|---|---|
| `"branded"` | `NomBrand – Niche Attributs` |
| `"characteristics"` | `Niche Attributs` (sans nom branding) |

### `branding_mode`
Comment le nom branding est choisi. Ignoré si `title_style = "characteristics"`.
| Valeur | Comportement |
|---|---|
| `"theme"` | Pioche dans la liste `brandingNames` (déterministe par produit) |
| `"ai"` | GPT génère un nom créatif unique par produit |

### `branding_position`
Position du nom branding dans le titre.
| Valeur | Exemple |
|---|---|
| `"start"` | `Atlas – Arbre à Chat XXL Hamac` |
| `"end"` | `Arbre à Chat XXL Hamac – Atlas` |

### `brandingNames`
Liste de noms utilisés en mode `branding_mode: "theme"`. Plus la liste est longue, plus les produits auront des noms variés. Les variantes de couleur d'un même produit réutilisent le même nom.

### `vendor`
Texte affiché après le `|` dans le meta title des produits.
- Ex : `"Arbre à Chat XXL Hamac Bois | Le Perchoir Du Chat"`

### `word_count`
Nombre minimum de mots dans la description HTML générée (entre 200 et 400).

### `generate_meta_description`
- `true` : génère la meta description via GPT
- `false` : ne génère que le titre, handle et description

### `generate_description`
- `true` : génère la description HTML `body_html`
- `false` : ne génère que le titre, handle et meta

### `mainCollection`
Collection principale utilisée pour le maillage interne dans les descriptions produit.
```json
"mainCollection": {
  "name":   "Arbre à Chat",
  "url":    "https://ma-boutique.com/collections/arbre-a-chat",
  "volume": 74000
}
```

### `collections`
Liste des collections à créer/mettre à jour via la feature **Collections**.
```json
"collections": [
  {
    "name":   "Arbre à Chat XXL",
    "volume": 1900,
    "tags":   ["arbre a chat xxl"],
    "url":    "https://ma-boutique.com/collections/arbre-a-chat-xxl"
  }
]
```
| Champ | Description |
|---|---|
| `name` | Nom affiché de la collection |
| `volume` | Volume de recherche mensuel (trié pour le maillage interne) |
| `tags` | Tags Shopify — les produits ayant ce tag sont inclus dans la collection |
| `url` | URL publique de la collection (utilisée pour le maillage interne) |

---

## Section `fiche_produit`

Utilisée par la feature **Fiche Produit**.

```json
"fiche_produit": {
  "niche_keyword": "Arbre à Chat"
}
```

| Champ | Description |
|---|---|
| `niche_keyword` | Même valeur que dans `seo_boost.niche_keyword` |

Les points de réassurance sont dans un fichier séparé :
`stores/{boutique}/fiche_produit/reassurance.md`

---

## Section `legal_info`

Utilisée par la feature **Politiques**.
À remplir **une seule fois** par boutique.

```json
"legal_info": {
  "company_name":    "Ma Société SAS",
  "email":           "contact@ma-boutique.com",
  "phone":           "+33 1 23 45 67 89",
  "address":         "123 rue de la Boutique, 75001 Paris, France",
  "siret":           "123 456 789 00012",
  "processing_time": "2-3 jours ouvrés",
  "shipping_delay":  "5-7 jours ouvrés",
  "website_url":     "https://www.ma-boutique.com"
}
```

| Champ | Description | Exemple |
|---|---|---|
| `company_name` | Nom légal de l'entreprise | `"Le Perchoir Du Chat SAS"` |
| `email` | Email de contact avec nom de domaine | `"contact@le-perchoir-du-chat.com"` |
| `phone` | Numéro de téléphone | `"+33 6 12 34 56 78"` |
| `address` | Adresse postale complète | `"12 rue des Chats, 75001 Paris"` |
| `siret` | Numéro SIRET (14 chiffres) | `"123 456 789 00012"` |
| `processing_time` | Délai de traitement commande | `"2-3 jours ouvrés"` |
| `shipping_delay` | Délai d'acheminement | `"5-7 jours ouvrés"` |
| `website_url` | URL publique du site (avec https://) | `"https://www.le-perchoir-du-chat.com"` |

---

## Où mettre les fichiers de contenu

Certaines features nécessitent des fichiers en plus de config.json :

```
stores/{boutique}/
├── config.json                        ← Ce fichier
│
├── reviews/                           ← Feature Reviews
│   ├── marketing.md                   ← Promesse produit, arguments de vente
│   ├── persona1.md                    ← Profil client 1
│   ├── persona2.md                    ← Profil client 2
│   └── persona3.md                    ← Profil client 3
│
├── fiche_produit/                     ← Feature Fiche Produit
│   └── reassurance.md                 ← Points de réassurance client
│
├── seo_boost/                         ← Feature SEO Boost + Collections
│   └── keywords.csv                   ← Mots-clés SEO avec volumes
│                                         Colonnes : Keyword, Volume
│
└── politiques/                        ← Feature Politiques
    ├── politique_retour.html          ← Politique de retour et remboursement
    ├── politique_confidentialite.html ← Politique de confidentialité
    ├── conditions_service.html        ← Conditions de service
    ├── politique_expedition.html      ← Politique d'expédition
    ├── coordonnees.html               ← Coordonnées
    ├── conditions_vente.html          ← Conditions de vente
    ├── mentions_legales.html          ← Mentions légales
    └── page_retour.html               ← Page "Politique De Retour" (/pages/return-policy)
```

---

## Comment préparer ses templates de politiques (Google Docs → HTML)

1. Ouvrir votre document Google Docs
2. **Fichier → Télécharger → Page Web (.html)**
3. Récupérer uniquement le contenu entre `<body>` et `</body>`
4. Nettoyer les styles inline générés par Google (optionnel)
5. Remplacer les informations spécifiques par les **placeholders** ci-dessous
6. Enregistrer le fichier dans `stores/{boutique}/politiques/`

### Placeholders disponibles dans les templates

| Placeholder | Remplacé par |
|---|---|
| `{{store_name}}` | Nom de la boutique |
| `{{company_name}}` | Nom de l'entreprise |
| `{{email}}` | Email de contact |
| `{{phone}}` | Téléphone |
| `{{address}}` | Adresse postale |
| `{{siret}}` | Numéro SIRET |
| `{{processing_time}}` | Délai de traitement |
| `{{shipping_delay}}` | Délai d'acheminement |
| `{{website_url}}` | URL publique du site |
| `{{url_retour}}` | Lien vers politique retour Shopify |
| `{{url_confidentialite}}` | Lien vers politique confidentialité |
| `{{url_conditions_service}}` | Lien vers conditions de service |
| `{{url_expedition}}` | Lien vers politique d'expédition |
| `{{url_coordonnees}}` | Lien vers coordonnées |
| `{{url_conditions_vente}}` | Lien vers conditions de vente |
| `{{url_mentions_legales}}` | Lien vers mentions légales |
| `{{url_page_retour}}` | Lien vers la page /pages/return-policy |

---

## Créer une nouvelle boutique

```bash
cp -r stores/_template/ stores/nom-de-ma-boutique/
```

Puis remplir dans cet ordre :
1. `config.json` — credentials + toutes les sections
2. `reviews/` — fichiers markdown personas et marketing
3. `fiche_produit/reassurance.md` — points de réassurance
4. `seo_boost/keywords.csv` — mots-clés SEO
5. `politiques/*.html` — templates depuis Google Docs avec placeholders

Lancer ensuite `python main.py` — la boutique apparaît automatiquement.
