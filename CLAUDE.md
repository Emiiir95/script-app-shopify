# CLAUDE.md — Shopify Automation

Documentation de l'infrastructure pour Claude Code.
**Lire ce fichier avant toute modification du code.**

---

## Vue d'ensemble

Application Python en ligne de commande qui automatise des opérations Shopify via les APIs REST et GraphQL.
Elle supporte plusieurs boutiques et plusieurs features indépendantes.

**Lancement :**
```bash
cd "/Users/emirsen/Desktop/app/script/GMC - shopify automatisé"
python main.py
```

**Dépendances Python :**
```bash
pip install requests openai tqdm
```

Au lancement : `main.py` demande la **boutique** puis affiche le **menu des features**
(voir la section « Menu des features & prérequis »). La session reste sur la même
boutique jusqu'à `q`.

---

## Architecture complète

```
script/
├── main.py                         ← Point d'entrée unique — sélection boutique + feature
├── .env                            ← OPENAI_API_KEY partagée entre toutes les boutiques
├── CLAUDE.md                       ← Ce fichier — documentation complète
│
├── stores/                         ← UN DOSSIER PAR BOUTIQUE — géré manuellement
│   ├── _template/                  ← Template à copier pour créer une nouvelle boutique
│   │   ├── config.json             ← Credentials Shopify (à remplir)
│   │   └── reviews/                ← Fichiers markdown pour la feature reviews
│   │       ├── marketing.md
│   │       ├── persona1.md
│   │       ├── persona2.md
│   │       └── persona3.md
│   │
│   └── atelier-veilleuse/          ← Boutique existante
│       ├── config.json             ← { name, store_url, access_token }
│       ├── reviews/                ← Contexte IA spécifique à cette boutique
│       │   ├── marketing.md        ← Promesse produit, bénéfices, arguments de vente
│       │   ├── persona1.md         ← Profil client type 1 (ex: parent)
│       │   ├── persona2.md         ← Profil client type 2 (ex: senior)
│       │   └── persona3.md         ← Profil client type 3 (ex: acheteur cadeau)
│       ├── reviews_preview.csv     ← Généré automatiquement avant injection
│       └── progress.json           ← Généré automatiquement — état de reprise
│
├── shopify/                        ← Couche API Shopify — PARTAGÉE entre toutes les features
│   ├── __init__.py
│   ├── client.py                   ← Client HTTP : GET/POST/PUT REST + GraphQL avec retry/rate limit
│   ├── products.py                 ← Fetch produits, lecture/écriture metafields produit
│   └── metaobjects.py              ← CRUD metaobjects et metaobject definitions (GraphQL only)
│
├── features/                       ← UNE FEATURE = UN SOUS-DOSSIER (toutes exposent run(store_config, store_path))
│   ├── __init__.py
│   ├── setup/                      ← 0. Crée la structure metafields / metaobjects
│   ├── seo_boost/                  ← 1. Titres, meta, description HTML, handle, specs (OpenAI)
│   ├── fiche_produit/              ← 2. Phrase, bénéfices, sections feature (OpenAI)
│   ├── fond_studio/                ← 3. Régénère la 1ère image produit sur fond uni (OpenAI gpt-image-1)
│   │   ├── runner.py  generator.py  injector.py  prompts.py
│   ├── normalisation/              ← 4. Prix, taxable, stock policy, couleurs (pas d'OpenAI)
│   ├── reviews/                    ← 5. Génération + injection d'avis clients (OpenAI)
│   │   ├── runner.py  generator.py  injector.py  setup.py  prompts.py
│   ├── seo_images/                 ← 6. Renommage fichiers + alt text
│   ├── collections/                ← 7. Création/maj collections + SEO (depuis config)
│   ├── politiques/                 ← 8. Politiques légales + page retour
│   ├── transfert/                  ← 9. Clone produits+metaobjects vers une autre boutique
│   │   ├── runner.py  exporter.py  importer.py   (pas de generator/prompts — pas d'OpenAI)
│   ├── menus/                      ← 10. Menus de navigation (depuis config)
│   │   ├── runner.py  injector.py
│   └── rebrand/                    ← 11. Remplacement URL/nom de marque (descriptions + SEO)
│       ├── runner.py  injector.py
│
├── utils/                          ← Utilitaires partagés entre toutes les features
│   ├── __init__.py
│   ├── logger.py                   ← Logger global — fichier logs/app.log + console optionnelle
│   ├── cost_tracker.py             ← Suivi tokens et coût USD des appels OpenAI
│   └── checkpoint.py              ← Sauvegarde/reprise progression (progress.json par boutique)
│
└── logs/
    └── app.log                     ← Généré automatiquement — tous les événements de toutes les sessions
```

---

## Système multi-boutiques

### Comment ça fonctionne

1. `main.py` scanne `stores/` et liste tous les dossiers qui ont un `config.json`
2. L'utilisateur choisit la boutique dans le terminal
3. `store_config` (dict) et `store_path` (chemin absolu) sont passés au runner de la feature
4. Chaque boutique a ses propres fichiers contexte, son CSV preview et son progress.json

### Structure d'un `config.json`

```json
{
  "name": "Nom affiché dans le terminal",
  "store_url": "nom-boutique.myshopify.com",
  "access_token": "shpat_xxxxxxxxxxxxxxxxxxxxxxxxxxxx"
}
```

### Comment ajouter une nouvelle boutique

1. Copier `stores/_template/` → `stores/nom-boutique/`
2. Remplir `stores/nom-boutique/config.json`
3. Remplir les fichiers markdown dans `stores/nom-boutique/reviews/`
4. Lancer `python main.py` → la boutique apparaît automatiquement

### Fichiers générés par boutique (runtime)

| Fichier | Contenu |
|---|---|
| `stores/{boutique}/reviews_preview.csv` | Aperçu des avis avant injection |
| `stores/{boutique}/progress_{feature}.json` | Checkpoint de reprise **par feature** (évite les collisions si plusieurs features tournent) |
| `stores/{boutique}/seo_boost_cache.json` | Cache de génération SEO (reprise avant injection) |
| `stores/{boutique}/rapports/*.csv` | Rapports horodatés (rebrand, normalisation, reviews) |
| `stores/{boutique}/backups/{feature}_{ts}.json` | Snapshot produits avant écrasement — **retour en arrière** (`utils/backup.py`) |
| `stores/{boutique}/.inject.lock` | Verrou d'injection temporaire (`utils/lock.py`) — présent seulement pendant qu'une feature écrit |
| `stores/{boutique}/generated/{feature}_{ts}.json` | **Archive permanente** de la data générée (`utils/archive.py`) — jamais effacée, 100% re-poussable |

---

## Menu des features & prérequis

Chaque feature est indépendante et se lance depuis le menu de `main.py`. **Chaque feature attend
une clé de configuration dans `config.json`** (sauf setup/transfert). Si la clé manque, la feature
affiche un message et ne fait rien — elle ne crashe pas.

| # | Feature | Clé `config.json` | OpenAI | À faire AVANT de lancer |
|---|---|---|---|---|
| 0 | Setup | — | non | Rien. À lancer en **premier** sur une nouvelle boutique. |
| 1 | SEO Boost | `seo_boost` | oui | La **description fournisseur** doit être dans le `body_html` de chaque produit (source de tout le contenu généré). Optionnel : `seo_boost/keywords.csv` (SEMrush). |
| 2 | Fiche Produit | `fiche_produit` | oui | Idem SEO Boost : description fournisseur dans `body_html`. |
| 3 | Fond Studio | `fond_studio` | oui (image) | Chaque produit doit avoir ≥ 1 photo. Définir `background_color`. ⚠ facturé par image (gpt-image-1). |
| 4 | Normalisation | `normalisation` | non | Rien. Préserve le status produit. Crée les couleurs manquantes (voir note couleurs). |
| 5 | Reviews | — (fichiers `.md`) | oui | Remplir `stores/{boutique}/reviews/*.md` + lancer Setup avant. |
| 6 | SEO Images | `seo_boost` (meta title) | non | Lancer SEO Boost avant (utilise le meta title comme base du nom de fichier). |
| 7 | Collections | `collections` | oui | Définir les collections dans `config.json`. |
| 8 | Politiques | `politiques` | non | Remplir les templates HTML dans `stores/{boutique}/politiques/`. |
| 9 | Transfert | — (choix interactif) | non | Avoir ≥ 2 boutiques dans `stores/`. La **destination** doit être vide ou acceptée en doublon. |
| 10 | Menus | `menus` | non | Collections/pages/politiques référencées doivent **exister** (créées avant). Scope navigation requis. |
| 11 | Rebrand | `rebrand` | non | Rien. À lancer typiquement **après un Transfert** pour changer marque/URL. |

**Ordre recommandé sur une boutique neuve :**
`0 Setup` → importer les produits (avec descriptions fournisseur) → `4 Normalisation` →
`1 SEO Boost` → `2 Fiche Produit` → `3 Fond Studio` → `7 Collections` → `10 Menus` →
`5 Reviews` → `8 Politiques` → `6 SEO Images`.
(`9 Transfert` + `11 Rebrand` = duplication d'une boutique existante vers une nouvelle.)

**Dépendance de titre (SEO Boost → Fiche Produit / Reviews) :** Fiche Produit (`product.title`)
et Reviews (`product["title"]`) génèrent leur contenu à partir du **titre du produit**. SEO Boost
**réécrit** ce titre (H1). Donc pour que Fiche/Reviews partent du titre optimisé, lancer **SEO Boost
d'abord**. Ce n'est pas bloquant (injection par ID produit), mais c'est mieux. Le backoffice affiche
un **guide d'ordre** (`renderOrderGuide`) sur les pages SEO Boost / Fiche Produit / Reviews et
**avertit** si SEO Boost n'a pas encore d'archive (`GET /api/generated` → `utils/archive.list_generated`).
La description source (body_html) est, elle, gérée dans tout ordre (metafield `custom.description_fournisseur`).

---

## Shopify API

### Règles importantes

- **Version API fixée dans `shopify/client.py`** : `SHOPIFY_API_VERSION = "2026-01"`
- **Metaobjects** : l'endpoint REST `/metaobjects.json` est **supprimé en 2026-01**. Toutes les opérations sur les metaobjects passent par **GraphQL**.
- **REST** : utilisé pour les produits, metafields produit (GET/POST/PUT).
- Le header `Retry-After` de Shopify peut être un float (`"2.0"`) → toujours parser avec `int(float(...))`.
- **Mutations supprimées à surveiller :** `shopPoliciesUpdate` (batch) → remplacé par
  `shopPolicyUpdate` (upsert, **une politique par appel**) dans `politiques/injector.py`.

### Scopes requis sur le token Shopify

La liste exhaustive à jour est dans **`champs-dacces.md`** (à copier/coller dans l'app custom Shopify).
Minimum par feature :

| Scope | Feature qui en a besoin |
|---|---|
| `read_products, write_products` | toutes |
| `read_metaobjects, write_metaobjects` | setup, reviews, normalisation, transfert |
| `read_metaobject_definitions, write_metaobject_definitions` | setup, transfert |
| `read_files, write_files` | reviews (photos), transfert (images) |
| `read_legal_policies, write_legal_policies` | politiques |
| `read_online_store_pages, write_online_store_pages` | politiques (page retour), menus |
| `read_online_store_navigation, write_online_store_navigation` | **menus** (sinon échec) |
| `read_content, write_content` | collections, menus (blogs) |
| `read_product_feeds, write_product_feeds` | export Google Merchant |

⚠️ **Après tout changement de scope, il faut régénérer/réinstaller le token** dans Shopify — les
anciens tokens gardent leurs anciens scopes.

### Fonctions disponibles dans `shopify/`

**`client.py`** :
- `shopify_get(url, headers, params)` — GET avec retry et rate limit
- `shopify_post(url, headers, payload)` — POST avec retry
- `shopify_put(url, headers, payload)` — PUT avec retry
- `graphql_request(base_url, headers, query, variables)` — GraphQL avec retry
- `shopify_headers(api_token)` — retourne le dict headers
- `shopify_base_url(store_url, api_version)` — retourne l'URL de base REST

**`products.py`** :
- `fetch_all_products(base_url, headers)` — récupère tous les produits (pagination auto)
- `fetch_product_metafields(product_id, base_url, headers)` — metafields d'un produit
- `missing_review_slots(metafields)` — liste des slots avis_clients_1-8 vides
- `set_product_metafield(product_id, namespace, key, value, type, base_url, headers)` — crée ou met à jour un metafield

**`metaobjects.py`** :
- `create_metaobject(review, base_url, headers)` — crée un metaobject avis_client (ACTIVE), retourne le GID
- `get_metaobject_definition_id(base_url, headers)` — retourne l'id de la définition avis_client
- `create_metaobject_definition(base_url, headers)` — crée la définition
- `create_metafield_definition(base_url, headers, name, key, field_type, mo_def_id)` — crée une metafield definition (ignore si déjà existante)

---

## OpenAI

- Modèle : `gpt-4o-mini`
- `response_format: json_object` pour garantir du JSON valide
- Temperature : `0.85` pour de la variété
- Coût suivi par `utils/cost_tracker.py` (prix au 2026-01 : $0.150/M input, $0.600/M output)

---

## Feature Reviews — détail

### Ce que la feature touche dans Shopify

**Uniquement ces 9 metafields** par produit (namespace `custom`) :

| Metafield | Type | Contenu |
|---|---|---|
| `note_globale_du_produit` | `single_line_text_field` | ex: `<strong>4.8</strong> \| 283+ avis vérifiés` |
| `avis_clients_1` à `avis_clients_8` | `metaobject_reference` | GID vers un metaobject `avis_client` |

**Metaobject `avis_client`** (champs) :

| Champ | Type |
|---|---|
| `note` | `single_line_text_field` — décimal entre 4.5 et 5.0 |
| `titre` | `single_line_text_field` |
| `texte` | `multi_line_text_field` |
| `nom_auteur` | `single_line_text_field` — format "Prénom I." |
| `photo_1` | `file_reference` (non rempli par le script) |
| `photo_2` | `file_reference` (non rempli par le script) |

### Logique du runner

1. Charge les fichiers markdown (contexte IA) depuis `store_path/reviews/`
2. Se connecte à Shopify + OpenAI
3. Vérifie/crée la structure metafields (demande à l'utilisateur si déjà fait)
4. Récupère tous les produits de la boutique
5. Filtre ceux qui n'ont pas leurs 8 avis (ou partiellement remplis)
6. Génère les avis manquants via GPT
7. Génère le CSV preview dans `store_path/reviews_preview.csv`
8. Demande validation utilisateur
9. Injecte : crée les metaobjects + remplit les metafields produit
10. Sauvegarde la progression après chaque produit (reprise automatique si crash)

---

## Feature Transfert (8) — cloner une boutique vers une autre

Copie **tout le catalogue** d'une boutique source vers une boutique destination, en recréant
les objets côté destination et en **remappant les GID** (les GID Shopify sont propres à chaque
boutique — une référence source ne fonctionne pas telle quelle sur la destination).

**Prérequis :**
- Au moins **2 boutiques** avec `config.json` valide dans `stores/`.
- Le token de la **destination** doit avoir les scopes d'écriture (produits, metaobjects,
  definitions, files).
- La source est la boutique déjà sélectionnée au démarrage ; la destination est choisie
  interactivement.

**Flow (`exporter.py` → `importer.py`) :** export (définitions metaobjects, metaobjects,
définitions metafields, produits active+draft+archived, metafields produit, URLs fichiers) →
résumé + confirmation → import dans cet ordre de dépendances :
1. Metaobject definitions → remap `{source_def_id: dest_def_id}`
2. Metafield definitions (remap des `mo_def_id` dans les validations)
3. Fichiers/images (re-upload via `fileCreate`, Shopify re-télécharge depuis l'URL)
4. Metaobjects (remap des `file_reference`)
5. Produits (remap `{source_product_id: dest_product_id}`, + liaison images↔variantes)
6. Metafields produit (remap `metaobject_reference` et `file_reference`)

**Notes :**
- Les types `shopify--*` (couleurs, taxonomie) sont **ignorés** à l'import (réservés Shopify).
- Un `file_reference` dont le fichier n'a pas pu être transféré est **sauté** (loggé), pas bloquant.
- Pas d'idempotence : relancer **recrée** les produits (doublons). À lancer sur une destination vide.

---

## Feature Menus (9) — navigation

Crée ou met à jour les menus de navigation depuis `config.json`. **Upsert** : si le menu existe
(par handle) il est mis à jour (`menuUpdate`), sinon créé (`menuCreate`) — fonctionne aussi sur
les menus par défaut non supprimables (`main-menu`, `footer`).

**Scope obligatoire :** `read_online_store_navigation, write_online_store_navigation`.

**Prérequis :** toutes les ressources référencées (collections, pages, blogs, politiques)
doivent **déjà exister** — sinon l'item est ignoré avec un warning. Lancer Collections/Politiques
avant.

**Structure `config.json` :**
```json
"menus": [
  {
    "title": "Menu principal",
    "handle": "main-menu",
    "items": [
      { "title": "Accueil",   "type": "frontpage" },
      { "title": "Boutique",  "type": "catalog" },
      { "title": "Griffoirs", "type": "collection", "handle": "griffoirs",
        "items": [ { "title": "XXL", "type": "collection", "handle": "griffoirs-xxl" } ] },
      { "title": "À propos",  "type": "page",  "handle": "a-propos" },
      { "title": "Retours",   "type": "shop_policy", "policy_type": "REFUND_POLICY" },
      { "title": "Blog",      "type": "blog",  "handle": "news" },
      { "title": "Promo",     "type": "http",  "url": "https://..." }
    ]
  }
]
```
Types supportés : `FRONTPAGE`, `CATALOG` (pas de ressource), `COLLECTION`/`PAGE`/`BLOG`
(champ `handle`), `SHOP_POLICY` (champ `policy_type`), `HTTP` (champ `url`).
Imbrication max **3 niveaux**.

---

## Feature Rebrand (10) — remplacement de marque

Applique une liste de remplacements texte `{from → to}` sur **3 champs** de chaque produit :
`descriptionHtml`, `seo.title`, `seo.description`. Cas d'usage : après un Transfert, remplacer
l'ancien nom de marque / ancienne URL dans tout le catalogue.

**Flow :** fetch produits (GraphQL) → calcul des changements (sans écrire) → aperçu (5 premiers)
+ compteurs → confirmation → injection `productUpdate` produit par produit → rapport CSV dans
`stores/{boutique}/rapports/`.

**Structure `config.json` :**
```json
"rebrand": {
  "replacements": [
    { "from": "ancien-site.com", "to": "nouveau-site.com" },
    { "from": "Ancienne Marque", "to": "Nouvelle Marque" }
  ]
}
```
Remplacement **littéral** (pas de regex), sensible à la casse, applique toutes les règles dans
l'ordre. Sûr à relancer (idempotent une fois les termes remplacés).

---

## Feature Fond Studio (3) — régénère la 1ère image sur fond uni

Pour chaque produit, envoie la **1ère photo** à **OpenAI gpt-image-1** (`images.edit`) avec un
prompt strict : remplacer le fond en gardant le produit **100 % identique et recentré**. Deux
types de fond (`background_type`) : **couleur unie** (`background_color`) ou **mise en scène**
(`scene_template` : minimaliste, luxe, mode, nature, beaute, maison, tech, cuisine, enfant, sport
— voir `SCENE_TEMPLATES` dans prompts.py). La nouvelle image est ajoutée en **position 1**
(l'ancienne 1ère est conservée, décalée).

**Flow (`generator.py` → `injector.py`) :** fetch produits avec images →
`download_image(url)` (requests) → `regenerate_on_background(...)` (gpt-image-1, renvoie du PNG) →
`add_first_image(product_id, bytes, alt, ...)` (REST `POST /products/{id}/images.json`,
`attachment` base64 + `position: 1`). Checkpoint par produit (reprise auto) + rapport CSV.

**Structure `config.json` :**
```json
"fond_studio": {
  "background_type":  "color",     // color | scene
  "background_color": "#FFFFFF",   // si color : hex (palette) ou nom : "beige"
  "scene_template":   "luxe",      // si scene : minimaliste|luxe|mode|nature|beaute|maison|tech|cuisine|enfant|sport
  "size":             "1024x1024", // optionnel : 1024x1024 | 1024x1536 | 1536x1024 | auto
  "output_format":    "png",       // optionnel : png | jpeg | webp
  "product_status":   "all",       // optionnel : all | active | draft (sinon demandé au lancement)
  "reference_images": 1            // optionnel : 1..4 images du produit envoyées à l'IA (plus fidèle mais + cher)
}
```
La qualité gpt-image-1 est fixée à **medium** (normale) côté appli — non configurable.

**Couleur de fond** — le prompt (`build_background_prompt`) demande EXACTEMENT la couleur choisie
(hex + RGB + interdictions de dérive/gradient), mais gpt-image-1 ne reproduit **jamais** un hex au
pixel près (limite des modèles d'image) : le fond sera proche et cohérent, pas rigoureusement exact.
Choix assumé : **100 % IA** (pas de post-traitement/découpage, pour garder des images naturelles).

**Notes :**
- **Payant** : chaque image est facturée par OpenAI (gpt-image-1, qualité medium). Le runner
  affiche une **estimation de coût** avant confirmation (~$0.05/image en 1024², ~$0.075 en portrait/paysage).
- Le prompt demande un produit **100 % identique** ET **recentré** (déplacé/redimensionné en bloc
  pour être centré, sans altérer son apparence).
- Rien n'est supprimé : l'ancienne 1ère image reste (en 2ème position).

---

## Note — préservation de la description fournisseur (SEO Boost 1 & Fiche Produit 2)

SEO Boost **écrase** `title`, `handle` et `body_html` du produit par le contenu généré.
Or la génération lit sa source dans `body_html`. Sans protection, un 2e run régénérerait
**par-dessus** le contenu déjà généré (compounding).

**Solution :** au 1er passage, `resolve_supplier_description()` (dans `seo_boost/runner.py`)
sauvegarde le `body_html` d'origine dans le metafield **`custom.description_fournisseur`**
(`multi_line_text_field`). Aux runs suivants, la génération lit **ce metafield** comme source,
jamais le `body_html` écrasé. → **SEO Boost et Fiche Produit sont relançables à volonté**, ils
régénèrent toujours depuis la vraie description fournisseur. Fiche Produit utilise le même helper.

⚠️ **Attention au tout premier run** : le backup capture le `body_html` **tel qu'il est à ce
moment**. Si SEO Boost a déjà tourné une fois *avant* l'introduction de cette logique (donc
`body_html` déjà généré, aucun backup), le backup figera ce contenu généré comme « source ».
Pour une base propre, réimporter les descriptions fournisseur dans `body_html` avant le 1er run.
Le metafield n'a pas besoin de définition (créé via REST) mais peut être ajouté dans Setup.

---

## Note — pousser la data déjà générée (sans OpenAI)

`features/push_saved/pusher.py` repousse vers Shopify la data **déjà générée** (donc payée),
**sans aucun appel OpenAI**. Sert quand des produits ont été sautés (features en parallèle).
Backoffice : bouton **« ⬆︎ Pousser ma data déjà générée »** (pages SEO Boost, Fiche Produit,
Reviews) → `POST /api/push-saved`. Réutilise les injecteurs existants.

**Deux sources, par ordre de priorité :**
1. **Archive permanente** `generated/{feature}_{ts}.json` (`utils/archive.py`) — écrite après
   chaque génération, **jamais effacée**, contient la data COMPLÈTE (caractéristiques SEO,
   descriptions Fiche Produit entières, avis complets). Push par **ID produit** (fiable).
2. **Fallback CSV d'aperçu** `rapports/*_preview.csv` (si pas d'archive) — data partielle
   (pas de caractéristiques, descriptions Fiche tronquées). Matching par handle (alias
   original↔nouveau car SEO change les handles).

Reviews ne remplit que les slots `avis_client` **vides** (recalculés au push → pas de doublon).
⚠️ Les données générées **avant** l'ajout de l'archive n'ont pas d'archive → seul le fallback CSV
(partiel) est dispo ; pour du complet, relancer la feature (créera l'archive).

## Note — retour en arrière (rollback)

**SEO Boost** écrase title/handle/body_html → snapshot avant écrasement dans
`stores/{boutique}/backups/seo_boost_{ts}.json` (`utils/backup.save_snapshot()`, indexé par
**ID produit**). Bouton **« ↩︎ Retour en arrière »** (page SEO Boost) → `GET /api/backups` +
`POST /api/rollback` (restaure le dernier snapshot title/handle/body_html + metafields).

**Fiche Produit & Reviews** n'écrasent rien (elles ne font qu'AJOUTER des metafields) → pas de
snapshot ; le retour en arrière **supprime les metafields écrits** (`features/reset/clearer.py`,
`FEATURE_METAFIELDS`) : fiche_produit = `custom.benefices/feature_1/feature_2/phrase` ;
reviews = `custom.avis_client_1..8/note_globale`. Bouton **« ↩︎ Retour en arrière »** (pages Fiche
Produit & Reviews) → `POST /api/rollback-feature`. Les metaobjects sous-jacents restent (invisibles,
ré-écrasés au prochain run). Re-poussable ensuite via « Pousser ma data ».

## Note — titres H1 naturels (SEO Boost 1)

Config `seo_boost.natural_titles` (bool, défaut `false`). `true` → au lieu du template rigide
`{niche} {attributs empilés}`, l'IA rédige un **H1 + meta title naturels** (`generate_natural_title`
/ `build_natural_title_prompt`, JSON `{h1, meta_title}`) : mot-clé/niche en tête **quand c'est
fluide**, sinon le **vrai nom du produit** (« Support à Colliers » plutôt que « Porte Bijoux Support
Collier »), pas de keyword-stuffing, ~50-65 car., respecte les `title_attributes` cochés, marque selon
`title_style`/`branding_position`. **Cible les mots-clés SEMrush** (`seo_keywords` = bloc
`format_keywords_for_prompt` issu de `keywords.csv`, avec volumes) → place les termes les plus
recherchés en tête. Option `seo_boost.title_use_image` (bool, nécessite `natural_titles`) : envoie
la **1ère photo** à l'IA (`image_url`, `detail:"low"` ≈ 85 tokens) pour un titre plus juste (couleur/
forme) ; le runner bascule alors sur `fetch_all_products_with_images`. Compatible avec l'unicité (retry `avoid` + `make_unique_title`)
et le mode thématique (le `niche_kw` passé est le type détecté). Repli sur le titre fournisseur si
l'IA échoue. `false` → ancien template (`build_h1` + `build_meta_title`). Conforme best practices
2026 (buyer-first, naturel, H1 ≈ meta title mais non identiques). UI : « Titres naturels ».

## Note — boutique mono-niche vs thématique (SEO Boost 1)

`build_h1` met la **niche fixe** (`seo_boost.niche_keyword`) au début de CHAQUE titre — conçu pour
une boutique **mono-niche**. Sur une boutique **thématique** (boîtes à montres, porte-bijoux,
armoires…), c'est faux : une boîte à montre devenait « Boîte à Bijoux ». Config `seo_boost.niche_mode` : `"fixed"` (défaut, mono-niche) ou `"thematic"`. En thématique, le
runner appelle `generate_product_type(product_title, supplier_description, niche_keyword, ..., niches=)`
par produit → le **vrai type** remplace `niche_kw` partout (H1, meta title/desc, description).
Si `seo_boost.niches` (liste fournie par l'utilisateur) est présent, l'IA **classe** le produit dans
UNE niche de la liste et `_snap_to_niche` **verrouille l'orthographe exacte** (tolère pluriel/casse/
accents/ponctuation ; si aucune ne correspond → garde la proposition IA). Sinon, type libre (2-5 mots).
Repli sur la niche fixe si l'IA échoue. UI : champs « Type de boutique » + « Les niches de ta boutique »
(liste, `showIf` thematic) sur la page SEO Boost.

## Note — titres/handles uniques (SEO Boost 1)

GPT génère le titre **produit par produit sans mémoire des autres** → il répète souvent le même
titre générique pour des produits similaires (ex : 10× « Boîte à Bijoux Design Bois Élégant »).
Le handle = `slugify(H1)` → handles identiques → **Shopify ajoute `-1`, `-2`…** (mauvais SEO).

**Unicité en 3 couches (respecte toujours les attributs cochés) :**
1. **Prompt** : instruction de varier le vocabulaire (synonymes style/commercial) pour que deux
   produits similaires n'aient pas le même libellé.
2. **Retry IA** : si le H1 est déjà pris, on redemande à GPT une variante distincte via le param
   `avoid=` de `build_boost_differentiator_prompt` / `generate_differentiator` (liste des titres
   pris) — jusqu'à 2 fois, dans les seuls attributs autorisés.
3. **Filet déterministe** : `make_unique_title` (ci-dessous) si l'IA n'a pas suffi.

**Unicité PAR BOUTIQUE (runs partiels / ajouts ultérieurs)** : au début de la génération, on amorce
`used_titles`/`used_handles` avec les titres/handles des produits **déjà en ligne** (via
`fetch_all_products`), en **excluant ceux du run en cours** (pour ne pas les bloquer avec leur propre
ancien titre). Ainsi un nouveau produit ajouté puis passé dans un run ultérieur évite les titres
existants → toujours unique à l'échelle de la boutique, jamais de `-N`. Même amorçage dans le push
archive (`_push_seo_from_archive`). Garantie testée jusqu'au pire cas (200 produits identiques → 200
titres/handles uniques).
`make_unique_title(h1, original_title, used_titles, title_attributes)` (seo_boost/runner.py)
dédoublonne en **respectant les cases cochées** (`title_attributes`) : si un H1 est déjà pris, il
greffe un détail distinctif du **titre fournisseur** pris UNIQUEMENT dans une catégorie **activée**
(vocabulaire par catégorie : `_COLOR_WORDS`, `_MATERIAL_WORDS`, `_STYLE_WORDS`, `_COMMERCIAL_WORDS`,
dimensions via `_DIM_RE`, feature = mots distinctifs restants). **Dernier recours** si deux produits
sont identiques sur toutes les catégories cochées : on départage avec une catégorie **décochée**
(ex : couleur pour « Cuir Noir » vs « Cuir Rose »), puis suffixe numérique si vraiment rien.
Appliqué à la génération ET au **push depuis l'archive** (`_push_seo_from_archive`, lit
`title_attributes` via `_read_title_attributes`) → réparer les URL en -N sans régénérer.
Sur atelier (dimensions+couleur décochées) : 75 titres uniques/121 → **121/121**.

## Note — cases à cocher du titre produit (SEO Boost 1)

`seo_boost.title_attributes` = dict `{clé: bool}` contrôlant les attributs autorisés dans le
titre (voir `TITLE_ATTRIBUTES` dans `seo_boost/prompts.py` : commercial_keyword, dimensions,
feature, material, style, color). Absent/clé manquante → `True`. Injecté dans le prompt du
differentiator (inclus + bloc « NE PAS INCLURE »). Tout décoché → differentiator vide (titre =
niche seule, sans appel OpenAI). UI backoffice = type de champ `checks`.

## Note — modes de titre H1 (SEO Boost 1)

Le H1 produit est construit algorithmiquement par `build_h1` selon la clé `title_style`
du bloc `seo_boost` (config.json). **3 modes** (exemple niche = "Griffoir Chat", SEO =
"XXL Sisal Beige", marque = "LumiNest") :

| `title_style` | Marque ? | SEO | Résultat |
|---|---|---|---|
| `characteristics` (défaut) | non | complet | `Griffoir Chat XXL Sisal Beige` |
| `branded` | oui | **court** (2 mots-clés) | `LumiNest – Griffoir Chat XXL Sisal` |
| `seo_branded` | oui | complet | `LumiNest – Griffoir Chat XXL Sisal Beige` |

- Les modes marqués (`branded`, `seo_branded`) utilisent `branding_mode` = `"ai"` (nom inventé
  par GPT) ou `"theme"` (pioché dans `brandingNames`), et `branding_position` = `"start"`/`"end"`.
- Le nombre de mots-clés SEO gardés en mode `branded` = constante `_BRANDED_SHORT_WORDS` (generator.py).
- Le meta title (`build_meta_title`) est indépendant et n'inclut jamais la marque.

---

## Note — Normalisation (4) : prix & couleurs

**Parties activables** (`normalisation.steps`, dict `{clé: bool}`) — la normalisation est découpée
en 5 parties **cochables indépendamment** (voir `resolve_steps` dans `injector.py`). Clé absente
ou `null` → **activée** (rétrocompatible : une config sans bloc `steps` fait tout comme avant) :
- `prix` : prix + prix barré (`compare_at_price`)
- `stock_taxes` : `taxable`, `inventory_policy`, `fulfillment_service`, `requires_shipping`
- `fournisseur` : `vendor` = nom boutique (le PUT produit est **sauté** si décoché)
- `categorie` : catégorie taxonomique Shopify
- `couleurs` : swatches `shopify--color-pattern` (le bloc de chargement/création couleurs est
  entièrement **sauté** dans le runner si décoché)

Une partie décochée est **laissée intacte** (aucun champ écrit). Si `prix` ET `stock_taxes` sont
décochés, le PUT variante est entièrement sauté. `normalize_product(..., steps=)` reçoit le dict
résolu ; le runner reflète l'état activé/désactivé dans le résumé avant confirmation. UI backoffice
= type de champ `checks` ; `price_mode` et les champs catégorie sont masqués (`showIf`) quand leur
partie est décochée.

**Catégorie par produit (boutique thématique)** — `normalisation.category_rules` (liste ordonnée
de `{match: [mots-clés], name: "Catégorie FR", search?: "terme forcé"}`). Chaque produit est classé
par `match_category_rule` (injector.py) : la **1ère règle** dont un mot-clé apparaît dans
`title + product_type + tags` (normalisés sans accent/casse, **mot entier**) gagne → **l'ordre = la
priorité** (mettre le plus spécifique en premier, ex : `montre` avant `boite` sinon « Boîte à Montre »
tomberait dans « Boîtes à bijoux »). `fetch_all_products_with_variants` récupère donc aussi
`product_type,tags`. Les GID sont résolus **une fois par terme** au lancement (`resolve_rule_gids`
→ `find_taxonomy_category_gid`, cache) ; le runner affiche chaque règle résolue/introuvable.
**Langue** : on cherche avec le **nom français** (`name`) — la taxonomie Shopify renvoie les noms
dans la langue de la boutique, donc pas besoin d'anglais ; `search` ne sert que de terme forcé si
la recherche FR échoue. Un produit sans règle correspondante prend `product_category_name`
(catégorie **par défaut / repli**). Boutique **mono-niche** : laisser `category_rules` vide et ne
remplir que `product_category_name`. UI backoffice = type de champ `catrules` (lignes mots-clés →
catégorie) + catégorie par défaut. Masqué si la partie `categorie` est décochée.

**Matching** : `match_category_rule` utilise la sémantique « **tous les mots présents** » (mots
entiers, sans accent/casse) — un mot-clé multi-mots comme `"boite montre"` exige `boite` ET `montre`
dans le titre/type/tags (ordre libre). C'est ce qui distingue « Boîte à Montre » de « Boîte à
Bijoux ». Un mot-clé mono-mot (`"armoire"`) marche toujours.

**Bouton « Récupérer les catégories »** (page Normalisation, widget `catrules`) : générique, marche
pour toute boutique (mono-niche ou thématique). L'utilisateur saisit ses niches (pré-remplies depuis
`seo_boost.niches`) → `POST /api/shopify/resolve-categories` → `resolve_categories` (server.py) →
`utils/taxonomy.suggest_categories`. Fonctionnement (`utils/taxonomy.py`) :
1. **Télécharge la taxonomie publique Shopify en français** (`TAXONOMY_URL`, `dist/fr/categories.txt`)
   et la met en cache (`cache/shopify_taxonomy_fr.txt`, TTL 30 j). Les **GID de catégorie sont
   universels** (identiques sur toutes les boutiques) → pas besoin de l'API Admin ni de deviner.
2. **Collecte des candidats** (`gather_candidates`) : pour chaque mot de la niche, toutes les
   catégories dont la feuille contient ce mot (couvre la dimension « porte » ET « bijoux ») + top
   lexical global.
3. **Choix de la plus proche** : si une clé OpenAI est dans `.env`, GPT tranche sémantiquement
   (`choose_category_ai` — gère les synonymes : « porte/arbre » → « Support pour bijoux », « porte
   montre » → « Présentoirs pour montres ») ; sinon repli lexical (`_score`). L'IA peut renvoyer le
   GID complet ou l'id court (`hb-2-3-2`) — les deux sont acceptés.

Le bouton remplit les lignes `mots-clés → catégorie (FR)` **et mémorise le GID exact** par ligne
(`row.dataset.gid`) → enregistré dans `category_rules[].gid` → **aucune recherche au lancement**
(`resolve_rule_gids` utilise le `gid` direct). Éditer le nom à la main efface le GID mémorisé (repli
recherche par nom). Niches sans catégorie → `found=False`, signalées pour correction. Le matching FR
(`dist/fr`) évite le problème de langue de l'API Admin (anglais). Tests : `tests/test_taxonomy.py`.

**Prix** (`normalisation.price_mode`) — le prix barré (`compare_at_price`) est **toujours vidé** ;
le prix final dépend du mode :
- `keep_price` : garde le prix actuel (ex : 20 / barré 50 → **20**)
- `use_compare` : met le prix barré comme prix (ex : 20 / barré 50 → **50** ; sécurité : jamais 0 si pas de barré)
- `max` (défaut) : garde le plus élevé (ex : 20 / barré 50 → **50**)
Config : `product_category_name` (fr), `product_category_search` (en), `price_mode`.

**Couleurs** : swatches via le metaobject standard **`shopify--color-pattern`** (⚠️ **pas**
`shopify--ct-color-pattern`, réservé à l'app payante Combined Listings). Créé automatiquement si
absent ; chaque couleur rattachée à la **taxonomie Shopify** (`color_taxonomy_reference` +
`pattern_taxonomy_reference` = "Solid") — mappings dans `_COULEUR_TAXONOMY_GID` / `_COULEUR_HEX`.
Couleur inconnue → fallback gris. **La normalisation ne modifie jamais le status du produit.**

---

## Utilitaires

### `utils/logger.py`

```python
from utils.logger import log, LOG_FILE

log("message")                          # log fichier uniquement
log("message", level="warning")         # niveaux : info, warning, error
log("message", also_print=True)         # log + print terminal
```

Le fichier log est dans `logs/app.log` (créé automatiquement).

### `utils/cost_tracker.py`

```python
from utils.cost_tracker import CostTracker

tracker = CostTracker()
tracker.add(response.usage)     # passe l'objet usage de la réponse OpenAI
print(tracker.summary())        # "Appels: X | Tokens: Y | Coût: $Z"
print(tracker.cost_usd)         # float
```

### `utils/checkpoint.py`

Checkpoint sauvegardé dans le dossier de la boutique. **Un fichier par feature**
(`progress_{feature}.json`) via le paramètre `feature=` — sinon plusieurs features
lancées en parallèle partageraient le même fichier et se sauteraient des produits
(une feature voit les `completed_handles` d'une autre → `continue`).

```python
from utils.checkpoint import save_progress, load_progress, clear_progress

last_index, completed_handles = load_progress(store_path, "seo_boost")
save_progress(store_path, idx, completed_handles, "seo_boost")
clear_progress(store_path, "seo_boost")
```

**Lancements en parallèle** : deux protections permettent de tout lancer d'un coup sans casse :
1. **Checkpoint par feature** (`progress_{feature}.json`) — plus de collision de reprise.
2. **Verrou boutique** (`utils/lock.py`, `StoreLock`) — la **phase d'injection** de chaque
   feature est entourée d'un verrou fichier (`stores/{boutique}/.inject.lock`). Une seule
   feature écrit à la fois ; les autres **attendent leur tour** puis injectent. La génération
   OpenAI reste parallèle (elle n'écrit pas sur Shopify). Verrou périmé (process mort ou
   > 30 min) volé automatiquement.

```python
from utils.lock import StoreLock
store_lock = StoreLock(store_path, "seo_boost")
store_lock.acquire(wait_message="  ⏳ Une autre feature ({feature}) écrit — attente...")
try:
    ...boucle d'injection...
finally:
    store_lock.release()
```

Reste conseillé de les lancer **dans l'ordre** (Menu des features) pour la lisibilité, mais ce
n'est plus obligatoire pour la correction.

---

## Conventions de code

### Règles générales

- Python 3.9+, pas de type hints obligatoires
- Chaque module a une docstring en haut expliquant son rôle
- Les fonctions publiques ont une docstring si leur signature n'est pas évidente
- Pas de classes sauf si vraiment justifié (seul `CostTracker` en a une)
- Les constantes en MAJUSCULES en haut de fichier

### Gestion d'erreurs

- Toutes les erreurs réseau sont gérées par les helpers `shopify_get/post/put` et `graphql_request` avec retry
- Dans les runners : `try/except` autour de chaque produit → continuer sur le suivant, ne jamais crasher
- Toujours logger l'erreur avec `log(msg, "error", also_print=True)` avant de continuer

### Signature des runners

Toutes les features doivent exposer une fonction `run` avec cette signature :

```python
def run(store_config: dict, store_path: str):
    """
    store_config : { name, store_url, access_token, openai_key }
    store_path   : chemin absolu vers stores/{boutique}/
    """
```

### Ajouter une nouvelle feature

1. Créer un dossier `features/nom_feature/` avec `__init__.py`, `runner.py`, `generator.py`, `injector.py`, `prompts.py`
2. Implémenter `run(store_config, store_path)` dans `runner.py`
3. Ajouter l'entrée dans `FEATURES` dans `main.py`
4. Ajouter les éventuels fichiers contexte dans `stores/_template/nom_feature/`
5. **Créer les tests unitaires** dans `tests/test_{nom_feature}_generator.py`, `tests/test_{nom_feature}_injector.py`, etc.

---

## Tests unitaires

### RÈGLE ABSOLUE

**Toute nouvelle fonction publique doit avoir ses tests unitaires.** Les tests se trouvent dans `tests/` et utilisent `unittest` + `unittest.mock` — pas de dépendances externes.

### Lancer les tests

```bash
# Utiliser le Python qui a les dépendances du projet (requests, tqdm, openai)
/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m unittest discover -s tests -t . -v
```

### Structure des tests

```
tests/                                   (~360 tests, tous mockés — aucun appel réseau réel)
├── __init__.py
├── test_client.py             ← shopify/client.py              (21)
├── test_products.py           ← shopify/products.py            (15)
├── test_metaobjects.py        ← shopify/metaobjects.py         (16)
├── test_generator.py          ← features/reviews/generator.py  (12)
├── test_injector.py           ← features/reviews/injector.py   (11)
├── test_prompts.py            ← features/reviews/prompts.py     (14)
├── test_setup.py              ← features/setup                 (13)
├── test_fond_studio_*.py      ← features/fond_studio (prompts/generator/injector) (15)
├── test_seo_images.py         ← features/seo_images            (32)
├── test_collections.py        ← features/collections           (49)
├── test_normalisation.py      ← features/normalisation         (22)
├── test_politiques.py         ← features/politiques            (40)
├── test_rebrand.py            ← features/rebrand/injector.py    (20)
├── test_menus.py              ← features/menus/injector.py      (20)
├── test_transfert_exporter.py ← features/transfert/exporter.py (14)
├── test_transfert_importer.py ← features/transfert/importer.py (22)
└── test_utils.py              ← utils/ (logger, cost_tracker, checkpoint) (38)
```

Les runners (orchestration + I/O interactif) ne sont pas testés unitairement — seule la
logique métier des `injector.py` / `exporter.py` / `generator.py` l'est.

### Ce qu'on teste

- **Comportement nominal** : la fonction retourne le bon résultat avec des inputs valides
- **Rate limiting** : 429 → sleep → retry → succès (avec parsing float du `Retry-After`)
- **Retry réseau** : `RequestException` → retry avec backoff exponentiel
- **Max retries** : lève l'exception après N tentatives
- **Cas limites** : fichier absent, JSON corrompu, liste vide, valeur "TAKEN" ignorée, etc.

### Règles pour écrire un test

```python
# Toujours mocker les appels réseau — jamais d'appels réels à Shopify/OpenAI
@patch("shopify.client.requests.get")
def test_success(self, mock_get):
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"products": []}
    mock_get.return_value = mock_resp

    result = shopify_get("http://example.com", {})
    self.assertEqual(result, {"products": []})
```

- Mocker au niveau du module qui importe (ex: `shopify.client.requests.get`, pas `requests.get`)
- Toujours mocker `time.sleep` pour ne pas ralentir les tests de retry
- Utiliser `tempfile.mkdtemp()` pour les tests qui écrivent des fichiers

---

## .env racine

Contient uniquement la clé OpenAI (partagée entre toutes les boutiques) :

```
OPENAI_API_KEY=sk-proj-...
```

Les credentials Shopify sont dans `stores/{boutique}/config.json`, pas dans `.env`.

---

## Fichiers à ne jamais modifier sans raison

| Fichier | Pourquoi |
|---|---|
| `shopify/client.py` | Couche réseau partagée — toute régression casse tout |
| `utils/logger.py` | Changer le format casse les logs existants |
| `stores/{boutique}/config.json` en prod | Credentials live |
