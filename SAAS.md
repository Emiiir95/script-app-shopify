# SAAS.md — Bible du projet (pour le futur Claude qui construit le SaaS)

> Lis ce fichier EN ENTIER avant de coder quoi que ce soit sur le SaaS.
> Il explique : ce qu'est le produit, ce que fait chaque feature, quelles données
> chacune a besoin, la couche Shopify/OpenAI, le backoffice actuel, et la base de
> données cible (modèle SaaS pay-as-you-go). Le détail technique du code actuel est
> dans `CLAUDE.md` ; ce fichier-ci donne la vue d'ensemble et la cible SaaS.

---

## 1. C'est quoi le produit

Un outil qui **automatise la mise en place d'une boutique Shopify** : à partir de
produits importés (avec juste la description brute du fournisseur), il génère et
injecte automatiquement tout le contenu d'une boutique pro : titres SEO, descriptions,
fiches produit, images sur fond studio, avis clients, collections, menus, pages légales,
normalisation des prix/stock, etc.

**Aujourd'hui** : app Python en ligne de commande (`main.py`) + un backoffice web local
(`backoffice/`) qui édite des fichiers `config.json` (un par boutique) et lance les
features via le terminal. Multi-boutiques, mono-utilisateur, tout en local.

**Cible (ce SaaS)** : la même logique, mais en **SaaS multi-utilisateurs** :
- comptes clients (auth, facturation),
- boutiques Shopify connectées en OAuth,
- réglages en base (plus de fichiers),
- exécutions (« runs ») lancées depuis une UI web, suivies et reprises,
- monétisation en **crédits pay-as-you-go** (achat de packs via Stripe, débit par run).

### Principe fondateur (à ne jamais oublier)
**Shopify est la SOURCE DE VÉRITÉ du catalogue.** Produits, collections, menus,
politiques, images, avis (metaobjects) vivent dans Shopify. Le SaaS **n'y duplique pas**
ces données : il les lit en direct via l'API, génère du contenu, l'injecte, et jette.
On ne stocke en base **que ce qui est à nous** : comptes, boutiques connectées, réglages
des features, jobs, crédits/paiements, audit.

---

## 2. Les 12 fonctionnalités (features)

Chaque feature est un module Python `features/<id>/runner.py` exposant
`run(store_config, store_path)`. Dans le SaaS, `store_config` viendra de la base
(colonne `stores.config` jsonb) au lieu d'un fichier.

Ordre du menu (le numéro n'est qu'un label d'affichage) :

| # | id (module) | Rôle en une phrase | OpenAI | Écrit dans Shopify |
|---|---|---|---|---|
| 0 | `setup` | Crée la structure metafields/metaobjects de la boutique | non | définitions metaobject + metafield |
| 1 | `seo_boost` | Titres, meta title/description, description HTML, handle, specs | gpt-4o | produit (title, body_html, handle, SEO, metafields) |
| 2 | `fiche_produit` | Phrase d'accroche, bénéfices, sections illustrées | gpt-4o / mini | metaobjects + metafields produit |
| 3 | `fond_studio` | Régénère la 1ère image produit sur un fond de couleur unie | gpt-image-1 | image produit (position 1) |
| 4 | `normalisation` | Prix, taxable, stock policy, couleurs, vendor | non | variantes + produit + metaobjects couleur |
| 5 | `reviews` | Génère et injecte des avis clients | gpt-4o-mini | metaobjects `avis_client` + metafields |
| 6 | `seo_images` | Renomme fichiers image + alt text via le meta title | non | fichiers/images (GraphQL fileUpdate) |
| 7 | `collections` | Crée/maj collections + SEO (description 1000+ mots, meta) | gpt-4o + mini | collections |
| 8 | `politiques` | Injecte les pages légales + page retour | non | politiques Shopify + page |
| 9 | `transfert` | Clone produits+metaobjects+images vers une autre boutique | non | tout le catalogue de la destination |
| 10 | `menus` | Crée/maj les menus de navigation | non | menus |
| 11 | `rebrand` | Cherche-remplace en masse (nom de marque / URL) | non | descriptions + SEO produits |

**La donnée d'entrée n°1 partout** : la **description fournisseur** dans le `body_html`
de chaque produit Shopify. C'est la matière première que l'IA reformule (SEO Boost,
Fiche Produit). Sans elle, le contenu généré est vide.

### Détail par feature (ce qu'elle fait + ce dont elle a besoin)

#### 0. Setup — `setup`
Crée dans Shopify les **définitions** metaobject (`avis_client`) et les metafield
definitions nécessaires aux autres features. **À lancer en premier** sur une boutique neuve.
**Données requises** : aucune (juste les identifiants Shopify).

#### 1. SEO Boost — `seo_boost`
Réécrit pour chaque produit : **titre H1**, **meta title** (titre Google), **meta
description** (résumé Google), **description HTML** (body_html), **handle** (URL),
**caractéristiques/specs**. Fait aussi du **maillage interne** (liens vers collections).
- Config `seo_boost` : `niche_keyword`, `title_style` (`characteristics` | `branded` |
  `seo_branded`), `branding_mode` (`theme` | `ai`), `branding_position` (`start` | `end`),
  `vendor`, `word_count` (200-400), `generate_meta_description`, `generate_description`,
  `brandingNames[]` (mode theme), `priorityTriggers` (`{"1":[…],"2":[…],"3":[…],"4":[…]}`),
  `mainCollection` (`{name,url,volume}`), `collections[]` (`{name,url,volume,tags,category}`).
- Fichier optionnel : `seo_boost/keywords.csv` (export SEMrush) → priorise les mots-clés.
- Modèle : **gpt-4o**. Cache de génération avant injection (reprise possible).
- 3 styles de titre : `characteristics` (SEO pur), `branded` (marque + SEO court),
  `seo_branded` (marque + SEO complet). Voir `build_h1`.

#### 2. Fiche Produit — `fiche_produit`
Génère le contenu enrichi des pages produits : phrase d'accroche, liste de bénéfices,
sections « feature » illustrées.
- Config `fiche_produit` : `niche_keyword`.
- Fichier requis : `fiche_produit/reassurance.md` (arguments de réassurance : livraison,
  garantie, paiement sécurisé…) → donne le ton à l'IA.
- Modèles : **gpt-4o** (bénéfices) + **gpt-4o-mini** (phrase, titres, descriptions).

#### 3. Fond Studio — `fond_studio`  *(feature IA image)*
Pour chaque produit, envoie la **1ère photo** à **gpt-image-1** (`images.edit`) avec un
prompt strict : remplacer **uniquement le fond** par une **couleur unie**, garder le
produit **100 % identique** et le **recentrer**. La nouvelle image devient la 1ère
(l'ancienne est conservée, décalée).
- Config `fond_studio` : `background_type` (`color` | `scene`), `background_color` (si color,
  hex ou nom), `scene_template` (si scene : minimaliste, luxe, mode, nature, beaute, maison,
  tech, cuisine, enfant, sport), `size`, `output_format` (`png` | `jpeg` | `webp`),
  `product_status` (`all` | `active` | `draft`), `reference_images` (1..4 : nb d'images du
  produit envoyées à l'IA en référence — plus = plus fidèle mais + cher).
- Modèle : **gpt-image-1**, qualité fixée « medium ». **Payant à l'image** (~$0.05 en
  1024², ~$0.075 en portrait/paysage). Le runner affiche une estimation avant lancement.
- ⚠ IA générative → rendu très fidèle mais pas garanti pixel-perfect.

#### 4. Normalisation — `normalisation`
Uniformise en masse : `price = max(price, compare_at_price)`, vide `compare_at_price`,
`taxable=false`, `inventory_policy=deny`, `fulfillment_service=manual`,
`requires_shipping=true`, `vendor = nom de la boutique`. **Ne change JAMAIS le status.**
Gère les swatches de couleur via le metaobject standard **`shopify--color-pattern`**
(⚠ pas `ct-color-pattern`, réservé à l'app payante).
- Config `normalisation` : `product_category_name` (fr), `product_category_search` (en),
  `price_mode` (`keep_price` = garde le prix | `use_compare` = met le prix barré comme prix |
  `max` = le plus élevé, défaut). Le prix barré est **toujours vidé**.

#### 5. Reviews — `reviews`
Génère des avis clients crédibles (note 4.5-5.0, titre, texte, « Prénom I. ») et les
injecte comme metaobjects `avis_client` + metafields (`avis_clients_1..8`,
`note_globale_du_produit`).
- Fichiers requis : `reviews/marketing.md`, `reviews/persona1.md`, `persona2.md`, `persona3.md`.
- Prérequis : lancer **Setup** avant. Modèle : **gpt-4o-mini**.

#### 6. SEO Images — `seo_images`
Renomme les fichiers image (`{meta-title-slug}-{position}.{ext}`) et met l'alt text =
meta title, via GraphQL `fileUpdate`. **Pas d'OpenAI.**
- Prérequis : lancer **SEO Boost** avant (utilise le meta title généré).
- ⚠ Piège connu : les noms de fichiers doivent être **uniques** dans toute la boutique ;
  sinon Shopify renvoie « filename already exists » (collisions entre produits ou re-run).

#### 7. Collections — `collections`
Crée/maj les collections et génère leur SEO : **description 1000+ mots**, **meta title**,
**meta description** (via GPT).
- Config : **réutilise** `seo_boost.collections` et `seo_boost.niche_keyword`.
- Modèle : **gpt-4o**.
- **Smart collections** (REST `/smart_collections.json`) : règle d'inclusion **`tag equals {nom
  de la collection}`** (+ les `tags` de config s'il y en a, en OR). Un produit taggé avec le nom
  de la collection y entre automatiquement. Voir `build_tag_rules` (injector.py).

#### 8. Politiques — `politiques`
Remplit les pages légales (mentions légales, CGV, retours, confidentialité, livraison,
remboursement, coordonnées) + une page retour. Upsert via GraphQL **`shopPolicyUpdate`**
(une politique par appel ; `shopPoliciesUpdate` batch a été supprimé par Shopify).
- Config `legal_info` : `company_name` (raison sociale), `email`, `phone`, `address`,
  `siret`, `processing_time`, `shipping_delay`, `website_url`.
- Fichiers : templates HTML dans `politiques/*.html` (les `{{placeholders}}` sont remplis
  par `legal_info`).

#### 9. Transfert — `transfert`
Clone **tout** le catalogue d'une boutique source vers une destination, en **remappant
les GID** (les GID Shopify sont propres à chaque boutique). Ordre : définitions metaobjects
→ définitions metafields → fichiers/images → metaobjects → produits → metafields produit.
- Données : aucune config ; destination choisie au lancement. Nécessite ≥ 2 boutiques et
  une destination vide (pas d'idempotence → relancer recrée des doublons).

#### 10. Menus — `menus`
Construit les menus de navigation (upsert par handle ; fonctionne sur les menus par défaut
`main-menu`, `footer`). **Scope `write_online_store_navigation` requis.**
- Config `menus[]` : `{title, handle, items[]}`. Types d'item : `FRONTPAGE`, `CATALOG`,
  `COLLECTION`/`PAGE`/`BLOG` (champ `handle`), `SHOP_POLICY` (`policy_type`), `HTTP` (`url`).
  Imbrication max 3 niveaux. Les ressources référencées doivent déjà exister.

#### 11. Rebrand — `rebrand`
Cherche-remplace **littéral** (sensible à la casse) sur `descriptionHtml`, `seo.title`,
`seo.description` de tous les produits. Idéal après un Transfert (changer nom de marque/URL).
- Config `rebrand.replacements[]` : `{from, to}`.

---

## 3. Couche Shopify (partagée par toutes les features)

- **Version API fixée** : `SHOPIFY_API_VERSION = "2026-01"` (dans `shopify/client.py`).
- **Metaobjects** : l'endpoint REST `/metaobjects.json` est **supprimé en 2026-01** → tout
  passe par **GraphQL**. REST reste pour produits, metafields produit, images.
- Header `Retry-After` peut être un float (`"2.0"`) → toujours `int(float(...))`.
- Mutations supprimées à connaître : `shopPoliciesUpdate` → remplacée par `shopPolicyUpdate`.
- Modules : `shopify/client.py` (GET/POST/PUT REST + GraphQL, retry + rate limit),
  `shopify/products.py` (fetch produits/variantes/images, metafields), `shopify/metaobjects.py`
  (CRUD metaobjects/définitions, GraphQL only).

### Scopes du token Shopify (liste dans `champs-dacces.md`)
Minimum par feature :

| Scope | Features |
|---|---|
| `read_products, write_products` | toutes |
| `read_metaobjects, write_metaobjects` | setup, reviews, fiche_produit, normalisation, transfert |
| `read_metaobject_definitions, write_metaobject_definitions` | setup, transfert |
| `read_files, write_files` | reviews (photos), seo_images, transfert, fond_studio |
| `read_legal_policies, write_legal_policies` | politiques |
| `read_online_store_pages, write_online_store_pages` | politiques, menus |
| `read_online_store_navigation, write_online_store_navigation` | **menus** |
| `read_content, write_content` | collections, menus (blogs) |
| `read_product_feeds, write_product_feeds` | export Google Merchant |

⚠ Après tout changement de scope → **régénérer/réinstaller le token** (les anciens gardent leurs scopes).

---

## 4. OpenAI

| Modèle | Utilisé par | Prix (au moment de l'écriture) |
|---|---|---|
| `gpt-4o` | seo_boost (titres/desc), collections (description longue), fiche_produit (bénéfices) | ~$2.5/M in, ~$10/M out |
| `gpt-4o-mini` | reviews, seo_boost (specs), collections (meta title/desc), fiche_produit (phrase/titres) | ~$0.15/M in, ~$0.60/M out |
| `gpt-image-1` | fond_studio | ~$0.04-0.075 / image (medium) |

- `response_format: json_object` pour garantir du JSON valide (features texte).
- Coûts suivis par `utils/cost_tracker.py` (tokens). Pour les images, estimation par image.
- **Clé OpenAI** : aujourd'hui dans `.env` racine (partagée). Dans le SaaS, c'est **ta** clé
  serveur (le client paie en crédits, pas en tokens) — voir « marge » dans `feature_runs`.

---

## 5. Le backoffice actuel (`backoffice/`)

Serveur HTTP Python **stdlib** (zéro dépendance), `python3 server.py` → http://localhost:4747.
Sert une SPA (`static/index.html` + `app.js` + `style.css`).

**API** : `GET /api/stores`, `GET/POST /api/store?folder=`, `GET/POST /api/file?store=&name=`,
`POST /api/store/create`, `GET /api/logs`, `POST /api/run` (ouvre un Terminal via AppleScript
et lance `main.py --store <folder> --feature <id>` → lancement direct).

**UI** : menu à gauche (11 features + Boutique + Mes données + Activité), formulaires générés
par un schéma (`FEATURES` dans `app.js`) où chaque champ a un `type` (text, select, bool,
color, list, collections, menus, pairs, triggers…). Verrouillage des features tant que la data
requise manque. Page Activité = lecture live de `logs/app.log`.

**Ce backoffice local est le prototype de l'UI SaaS.** Dans le SaaS, il faudra le reconstruire
en vraie app web multi-utilisateurs (auth, DB, jobs asynchrones au lieu d'ouvrir un Terminal).

---

## 6. La base de données SaaS (`bdd.dbml`)

Modèle Postgres, PK en `uuid` (`gen_random_uuid()`) sauf `migrations`. À coller dans
dbdiagram.io. **On ne duplique pas le catalogue Shopify** — voir principe fondateur.

### 6.0 — Auth & sécurité
- **`user`** : compte client (email, password hash, rôle, infos facturation, `stripe_customer_id`).
  Possède N boutiques + 1 wallet de crédits.
- **`user_token`** : jetons applicatifs (access, refresh, vérif email, reset mdp). Cascade sur delete user.
- **`migrations`** : historique ORM (ne pas éditer à la main).
- **`rate_limit_attempt`** : anti brute-force (compte les tentatives par cible+identifiant).
- **`audit_log`** : journal **append-only** de toute action sensible (login, connexion boutique,
  run lancé, crédits achetés…). Ne jamais UPDATE/DELETE. Sert aux enquêtes fraude/piratage.

### 6.1 — Boutiques
- **`stores`** : 1 boutique Shopify connectée par ligne. Champ clé : **`config` (jsonb)** =
  l'équivalent du `config.json` actuel (1 clé par feature : `seo_boost`, `fiche_produit`,
  `fond_studio`, `normalisation`, `collections`, `menus`, `rebrand`, `legal_info`…).
  `access_token` **à chiffrer** en base. Unique `(user_id, store_url)`.
- **`ai_context_file`** : le contexte IA rédigé par l'user (marketing, persona1/2/3, reassurance).
  Remplace `stores/{boutique}/reviews/*.md` et `fiche_produit/reassurance.md`. Unique `(store_id, kind)`.

### 6.2 — Jobs (exécutions de features)
- **`feature_runs`** : un run = une feature lancée sur une boutique. Remplace `progress.json`
  et le CostTracker. Colonnes clés :
  - `params` (jsonb) : entrées du run (options, produits ciblés, boutique dest…),
  - `progress` (jsonb) : reprise (handles/ids traités, last_index),
  - `preview` (jsonb) : **contenu généré EN ATTENTE de validation** ; vidé après injection Shopify
    (le contenu IA n'a pas de table dédiée — il est temporaire),
  - `credits_estimated` / `credits_spent`,
  - coûts internes OpenAI (`openai_*`, `cost_usd`) = **ta marge**, pas facturé tel quel,
  - `status` (enum `run_status` : pending, running, awaiting_validation, completed, failed,
    interrupted, cancelled).

### 6.3 — Crédits & paiements (pay-as-you-go, Stripe one-time)
Modèle **crédits** : le client achète des packs, chaque run débite des crédits.
- **`feature_pricing`** : barème = combien de crédits coûte chaque feature (par produit).
  Modifiable sans redéploiement (ex : `seo_boost=1`, `collections=2`, `fond_studio=2`,
  features non-IA = 0).
- **`credit_pack`** : catalogue des packs achetables (miroir des Prices Stripe one-time).
  La vérité du tarif = Stripe.
- **`credit_wallet`** : 1 portefeuille par user. `balance`/`total_*` sont des **caches** ;
  la vérité = le ledger.
- **`payment`** : un achat de pack (miroir Stripe Checkout `mode=payment`). `paid` via webhook
  → crédite le wallet. Idempotence via `stripe_checkout_session_id`.
- **`credit_transaction`** : **LEDGER append-only** — chaque mouvement de crédits (signé :
  + achat/bonus/refund, − consommation). **Solde = SUM(amount).** Ne jamais UPDATE/DELETE.
  `run_id` si consommation, `payment_id` si achat.
- **`stripe_event`** : journal des webhooks Stripe pour **idempotence** (enregistrer AVANT de
  traiter ; si `stripe_event_id` déjà présent → skip).

### Flux crédits (à implémenter dans le SaaS)
1. Achat : Checkout Stripe → webhook `checkout.session.completed` → `stripe_event` (idempotence)
   → `payment.status=paid` → `credit_transaction` (type `purchase`, +crédits) → maj cache `credit_wallet`.
2. Run : avant lancement, estimer les crédits (`feature_pricing × nb produits`) → vérifier
   `wallet.balance` suffisant → lancer `feature_runs` → à la fin, `credit_transaction`
   (type `consumption`, −crédits, `run_id`) → maj cache.
3. Le **solde réel** se recalcule toujours par `SUM(credit_transaction.amount)` ; `balance`
   n'est qu'un cache d'affichage.

---

## 7. Migration fichiers → SaaS (correspondances)

| Aujourd'hui (fichiers) | Demain (base) |
|---|---|
| `stores/{b}/config.json` (racine : name, store_url, access_token) | `stores` (name, store_url, access_token chiffré) |
| `stores/{b}/config.json` (blocs feature) | `stores.config` (jsonb) |
| `stores/{b}/reviews/*.md`, `fiche_produit/reassurance.md` | `ai_context_file` |
| `stores/{b}/progress.json` | `feature_runs.progress` |
| `stores/{b}/*_cache.json` (preview avant injection) | `feature_runs.preview` |
| `stores/{b}/rapports/*.csv` | `feature_runs` + `audit_log` (ou table de rapports si besoin) |
| CostTracker (tokens) | `feature_runs.openai_*` + `cost_usd` |
| `.env` OPENAI_API_KEY (par app) | clé serveur unique (la tienne) ; le client paie en crédits |
| Backoffice local (ouvre un Terminal) | UI web + workers/jobs asynchrones |

**Le cœur métier (les `features/*/runner.py`) est réutilisable tel quel** : il suffit de lui
passer un `store_config` construit depuis la base au lieu du fichier, et de remplacer les
lectures/écritures fichiers (progress/cache) par des accès `feature_runs`.

---

## 8. Conventions & pièges à connaître

- **Shopify = source de vérité** : ne jamais dupliquer le catalogue en base.
- **Idempotence** : Transfert n'est PAS idempotent (recrée des doublons) ; SEO Images échoue
  sur « filename already exists » si re-run (noms non uniques) → à corriger côté génération.
- **Metaobjects couleur** : utiliser `shopify--color-pattern` (pas `ct-`).
- **Politiques** : `shopPolicyUpdate` (upsert, 1 par appel), pas `shopPoliciesUpdate`.
- **Scopes** : régénérer le token après tout changement ; menus exige `write_online_store_navigation`.
- **Tests** : toute fonction publique a ses tests (`tests/`, `unittest` + `mock`, tout mocké,
  aucun appel réseau réel). ~391 tests. Lancer :
  `/Library/Frameworks/Python.framework/Versions/3.13/bin/python3 -m unittest discover -s tests -t . -v`
- **Sécurité SaaS** : chiffrer les `access_token` Shopify ; `audit_log` et `credit_transaction`
  sont append-only ; idempotence des webhooks Stripe via `stripe_event`.
- **Ledger** : le solde de crédits se recalcule par somme du ledger ; `credit_wallet.balance`
  n'est qu'un cache.

---

## 9. Où lire quoi

| Fichier | Contenu |
|---|---|
| `SAAS.md` (ce fichier) | Vue d'ensemble + cible SaaS + BDD |
| `CLAUDE.md` | Détail technique du code actuel (features, API, tests, conventions) |
| `bdd.dbml` | Schéma de la base SaaS (dbdiagram.io) |
| `LANCER.md` | Comment lancer le CLI + le backoffice en local |
| `champs-dacces.md` | Liste exhaustive des scopes du token Shopify |
| `features/<id>/` | Code de chaque feature (runner, generator, injector, prompts) |
| `backoffice/` | Prototype UI web (schéma des champs dans `static/app.js`) |
