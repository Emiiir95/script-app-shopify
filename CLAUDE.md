# CLAUDE.md — Shopify Automation

Documentation de l'infrastructure pour Claude Code.
**Lire ce fichier avant toute modification du code.**

---

## Vue d'ensemble

Application Python en ligne de commande qui automatise des opérations Shopify via les APIs REST et GraphQL.
Elle supporte plusieurs boutiques et plusieurs features indépendantes.

**Lancement :**
```bash
cd /Users/emirsen/Desktop/script
python main.py
```

**Dépendances Python :**
```bash
pip install requests openai tqdm
```

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
├── features/                       ← UNE FEATURE = UN SOUS-DOSSIER
│   ├── __init__.py
│   │
│   ├── reviews/                    ← Feature : génération et injection d'avis clients
│   │   ├── __init__.py
│   │   ├── runner.py               ← Orchestration — reçoit (store_config, store_path), appelle tout
│   │   ├── generator.py            ← Appels OpenAI — génère les avis en JSON
│   │   ├── injector.py             ← Injection Shopify — crée metaobjects + remplit metafields
│   │   ├── setup.py                ← Création structure Shopify — metaobject def + metafield defs
│   │   └── prompts.py              ← Tous les prompts OpenAI — system prompt + user prompt
│   │
│   └── titles/                     ← Feature à venir — réécriture des titres produit
│       ├── __init__.py
│       ├── runner.py               ← À coder — même signature : run(store_config, store_path)
│       ├── generator.py            ← À coder — génération titres via OpenAI
│       ├── injector.py             ← À coder — PUT produit title via REST
│       └── prompts.py              ← À coder — prompts pour titres
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
| `stores/{boutique}/progress.json` | Checkpoint pour reprise automatique |

---

## Shopify API

### Règles importantes

- **Version API fixée dans `shopify/client.py`** : `SHOPIFY_API_VERSION = "2026-01"`
- **Metaobjects** : l'endpoint REST `/metaobjects.json` est **supprimé en 2026-01**. Toutes les opérations sur les metaobjects passent par **GraphQL**.
- **REST** : utilisé pour les produits, metafields produit (GET/POST/PUT).
- Le header `Retry-After` de Shopify peut être un float (`"2.0"`) → toujours parser avec `int(float(...))`.

### Scopes requis sur le token Shopify

```
read_products, write_products
read_metaobjects, write_metaobjects
read_files, write_files
```

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

Le progress.json est sauvegardé dans le dossier de la boutique, pas à la racine.

```python
from utils.checkpoint import save_progress, load_progress, clear_progress

last_index, completed_handles = load_progress(store_path)
save_progress(store_path, idx, completed_handles)
clear_progress(store_path)
```

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
tests/
├── __init__.py
├── test_client.py       ← shopify/client.py     (21 tests)
├── test_products.py     ← shopify/products.py   (13 tests)
├── test_metaobjects.py  ← shopify/metaobjects.py (16 tests)
├── test_generator.py    ← features/reviews/generator.py (13 tests)
├── test_injector.py     ← features/reviews/injector.py  (11 tests)
├── test_prompts.py      ← features/reviews/prompts.py   (14 tests)
└── test_utils.py        ← utils/ (logger, cost_tracker, checkpoint) (27 tests)
```

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
