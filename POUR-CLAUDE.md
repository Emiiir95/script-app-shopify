# POUR-CLAUDE.md — Faire tout faire par Claude Code

Ce fichier a deux parties :

- **Partie 1** : pour **toi**, l'utilisateur non-développeur. Ce que tu installes,
  et les phrases exactes à copier-coller.
- **Partie 2** : pour **Claude Code**. Il la lit et sait quoi faire. Tu n'as pas
  besoin de la comprendre.

---
---

# PARTIE 1 — Pour toi

## A. Installer Claude Code (une seule fois)

Le plus simple sur Mac : **l'application de bureau**.

1. Va sur **https://claude.com/download**
2. Télécharge et installe l'app Claude, puis connecte-toi à ton compte Anthropic.
3. Dans l'app, choisis **Claude Code**, puis ouvre le dossier du projet
   (`script-app-shopify-main`, celui qui contient `main.py`).

> Claude Code nécessite un abonnement Claude payant (Pro ou Max), ou un compte
> API avec du crédit. C'est **séparé** de la clé OpenAI dont l'outil a besoin
> pour générer les textes : ce sont deux abonnements différents.

## B. Les phrases à copier-coller

Une fois Claude Code ouvert **dans le dossier du projet**, copie-colle ces
phrases telles quelles, dans l'ordre. Attends qu'il ait fini avant la suivante.

### 1️⃣ La toute première fois — installation

```
Lis POUR-CLAUDE.md et fais la procédure INSTALLER.
```

### 2️⃣ Ajouter ta boutique Shopify

```
Lis POUR-CLAUDE.md et fais la procédure CONFIGURER. Guide-moi pour trouver
les informations dont tu as besoin.
```

### 3️⃣ Ouvrir le backoffice (l'interface de réglages)

```
Lis POUR-CLAUDE.md et fais la procédure OUVRIR-BACKOFFICE.
```

### 4️⃣ Lancer un traitement sur ta boutique

```
Lis POUR-CLAUDE.md et fais la procédure LANCER.
```

Il te demandera quelle boutique et quelle fonctionnalité, en français.

### 5️⃣ Si quelque chose ne marche pas

```
Lis POUR-CLAUDE.md et fais la procédure DÉPANNER. Voici mon problème : [décris
ce que tu vois]
```

### 6️⃣ Si un traitement a donné un mauvais résultat

```
Lis POUR-CLAUDE.md et fais la procédure ANNULER.
```

## C. Ce que tu ne dois pas faire

- **Ne demande pas à Claude de modifier le code** de l'outil. S'il te propose
  d'« améliorer » ou de « corriger » quelque chose dans les fichiers `.py`,
  dis non et préviens la personne qui t'a donné l'outil.
- **Ne colle jamais ton token Shopify ou ta clé OpenAI dans un message public**
  (Discord, GitHub, e-mail…).

---
---

# PARTIE 2 — Pour Claude Code

**Tu parles à un utilisateur non-développeur.** Applique ces règles pour tout ce
qui suit :

- Parle **français**, en langage courant. Pas de jargon : dis « le dossier de ta
  boutique », pas « le répertoire `stores/<folder>` ».
- **N'explique pas ce que tu fais techniquement.** Exécute, et rends compte en
  une ou deux phrases.
- **Ne modifie jamais le code source** (`main.py`, `features/`, `shopify/`,
  `utils/`, `backoffice/`). Tu es ici pour *faire tourner* l'outil, pas pour le
  développer. Si tu détectes un vrai bug, décris-le à l'utilisateur et dis-lui
  d'en parler à la personne qui lui a fourni l'outil. N'essaie pas de le
  réparer toi-même.
- Les seuls fichiers que tu as le droit d'écrire sont : `.env` et le contenu de
  `stores/<boutique>/`.
- **Ne fais jamais `git commit` ni `git push`.** Les fichiers de configuration
  contiennent des identifiants.
- N'affiche jamais en entier un token `shpat_…` ni une clé `sk-…`. Pour
  confirmer qu'ils sont présents, montre seulement les 4 derniers caractères.

---

## Procédure INSTALLER

1. Vérifie Python : `python3 --version`.
   S'il est absent, dis à l'utilisateur d'installer Python depuis
   **https://www.python.org/downloads/**, puis de te redemander la procédure.
   **Ne tente pas d'installer Python toi-même** (Homebrew, etc.).
2. Crée l'environnement isolé s'il n'existe pas : `python3 -m venv .venv`
3. Installe les dépendances : `.venv/bin/python -m pip install -r requirements.txt`
   **Toujours dans le `.venv`, jamais en global.**
4. Confirme en une phrase : « C'est installé, tu peux passer à la configuration. »

---

## Procédure CONFIGURER

### Étape A — la clé OpenAI

L'outil génère les textes avec l'IA d'OpenAI. Il lui faut une clé.

1. Regarde si un fichier `.env` existe à la racine et contient `OPENAI_API_KEY=`
   avec une valeur non vide. Si oui, passe à l'étape B.
2. Sinon, demande la clé à l'utilisateur en lui expliquant :
   - elle se crée sur **https://platform.openai.com/api-keys**
   - elle commence par `sk-`
   - **elle est payante à l'usage** — conseille-lui de fixer une limite de
     dépense mensuelle dans les réglages de son compte OpenAI
3. Écris-la dans `.env` à la racine, au format `OPENAI_API_KEY=sk-...`
   (crée le fichier s'il n'existe pas ; ne touche pas aux autres lignes).

### Étape B — la boutique Shopify

1. Demande le **nom** de la boutique (libre, ex. « Perchoir du Chat »).
2. Crée le dossier `stores/<nom-en-minuscules-avec-tirets>/` en copiant
   **tout** le contenu de `stores/_template/` (config.json + sous-dossiers).
3. Demande les deux identifiants Shopify, en expliquant où les trouver :

   | Info | Où la trouver |
   |---|---|
   | L'adresse `xxx.myshopify.com` | Dans la barre d'adresse de l'admin Shopify |
   | Le token `shpat_…` | Admin Shopify → Paramètres → Applications et canaux de vente → Développer des applications → Créer une application → onglet Configuration → Admin API → cocher les scopes → Enregistrer → Installer l'application → Révéler le token |

   Les scopes à cocher sont la liste exacte du fichier **`champs-dacces.md`**.
   Affiche-la-lui telle quelle, c'est du copier-coller dans Shopify.

4. Renseigne `name`, `store_url` et `access_token` dans
   `stores/<boutique>/config.json`.
5. Vérifie que le token fonctionne avant d'aller plus loin :

   ```bash
   .venv/bin/python -c "
   import json,sys,requests
   from shopify.client import SHOPIFY_API_VERSION
   c=json.load(open(sys.argv[1]))
   r=requests.get(f\"https://{c['store_url']}/admin/api/{SHOPIFY_API_VERSION}/shop.json\",
                  headers={'X-Shopify-Access-Token':c['access_token']},timeout=20)
   print(r.status_code, r.json().get('shop',{}).get('name','') if r.ok else r.text[:200])
   " stores/<boutique>/config.json
   ```

   - `200` + le nom de la boutique → c'est bon, dis-le-lui.
   - `401` / `403` → le token est faux ou il manque des scopes. Renvoie-le à
     l'étape 3, ne bricole pas.

6. Dis-lui que le reste des réglages (style des titres, longueur des textes,
   avis clients…) se fait dans le backoffice, et que le détail de chaque
   réglage est documenté dans **`CONFIG.md`** — que tu peux lui expliquer
   réglage par réglage s'il le demande.

---

## Procédure OUVRIR-BACKOFFICE

Le backoffice est l'interface web de réglages, sur http://localhost:4747.

1. S'il tourne déjà (`curl -s -o /dev/null http://localhost:4747` répond),
   dis-le et ouvre simplement l'adresse : `open http://localhost:4747`
2. Sinon, lance-le **en tâche de fond** : `.venv/bin/python backoffice/server.py`
   puis ouvre `http://localhost:4747`.
3. Préviens-le de **cliquer « Enregistrer »** après chaque modification, avant
   de lancer quoi que ce soit.

Pour l'arrêter, il suffit de te le demander.

---

## Procédure LANCER

### Les fonctionnalités disponibles

| N° | Nom | Ce que ça fait |
|---|---|---|
| 0 | Setup | Crée la structure metafields / metaobjects (**à faire en premier** sur une boutique neuve) |
| 1 | SEO Boost | Titres, descriptions, meta titles, handles, specs produits |
| 2 | Fiche Produit | Phrase d'accroche, bénéfices, sections avec images |
| 3 | Fond Studio | Régénère la 1ʳᵉ image produit sur fond uni (IA) |
| 4 | Normalisation | Prix, taxes, gestion du stock, statut des produits |
| 5 | Reviews | Génère et injecte des avis clients |
| 6 | SEO Images | Renomme les fichiers images + textes alternatifs |
| 7 | Collections | Crée / met à jour les collections + leur SEO |
| 8 | Politiques | Injecte les politiques légales + page retour |
| 9 | Transfert | Copie produits + metaobjects vers une autre boutique |
| 10 | Menus | Crée / met à jour les menus de navigation |
| 11 | Rebrand | Remplace URL / nom de marque dans les textes et le SEO |

### Marche à suivre

1. Demande **quelle boutique** (liste les dossiers de `stores/`, hors `_template`)
   et **quelle fonctionnalité** (montre le tableau ci-dessus).

2. ⚠️ **Avertis-le avant de lancer** : ces traitements **modifient pour de vrai
   les produits de la boutique en ligne**. Demande une confirmation explicite.
   Si c'est sa première utilisation sur cette boutique, recommande-lui de tester
   d'abord sur une boutique de développement Shopify, ou sur un petit nombre de
   produits.

3. Rappelle-lui de vérifier ses réglages dans le backoffice et d'avoir
   **enregistré** avant.

4. Lance :

   ```bash
   .venv/bin/python main.py --store <dossier-boutique> --feature <numéro>
   ```

   Le programme est **interactif** : il pose des questions dans le terminal.
   Si tu ne peux pas répondre à sa place, **n'invente pas de réponses** —
   affiche la question à l'utilisateur, demande-lui quoi répondre, et
   transmets. En cas de doute sur une question, demande, ne devine pas.

5. Quand c'est fini, résume en français ce qui a été modifié et combien de
   produits sont concernés. En cas d'erreur, regarde `logs/app.log` et
   explique le problème en langage simple.

---

## Procédure ANNULER

L'outil prend un instantané (snapshot) avant les traitements qui modifient les
produits, donc un retour arrière est souvent possible.

1. Demande quelle boutique et quelle fonctionnalité doit être annulée.
2. Ouvre le backoffice (procédure OUVRIR-BACKOFFICE) : la restauration se pilote
   depuis l'interface, qui liste les sauvegardes disponibles.
3. Si aucune sauvegarde n'existe pour ce traitement, **dis-le clairement** au
   lieu de tenter une correction manuelle produit par produit. Explique-lui
   qu'il devra corriger depuis l'admin Shopify, ou en relançant le traitement
   avec de meilleurs réglages.

---

## Procédure DÉPANNER

| Symptôme | Cause et réponse |
|---|---|
| `command not found: python3` | Python n'est pas installé → procédure INSTALLER, étape 1 |
| `Address already in use` | Le backoffice tourne déjà → ouvre juste http://localhost:4747 |
| `ModuleNotFoundError` | Dépendances manquantes ou lancé hors du `.venv` → refais la procédure INSTALLER, et utilise toujours `.venv/bin/python` |
| `401` / `403` de Shopify | Token invalide ou scopes manquants → procédure CONFIGURER, étape B3 |
| Erreur OpenAI `401` | Clé OpenAI invalide → procédure CONFIGURER, étape A |
| Erreur OpenAI `429` / quota | Plus de crédit sur le compte OpenAI, ou trop de requêtes → il doit recharger son compte OpenAI |
| La page web est bizarre / pas stylée | Recharger avec `Cmd+Shift+R` |
| macOS refuse d'ouvrir `Lancer.command` | Clic droit → Ouvrir (voir `INSTALLATION.md`) |
| Le traitement s'arrête au milieu | Regarde `logs/app.log`, résume l'erreur en français |

Si le problème n'est dans aucune case : lis `logs/app.log`, explique en langage
simple ce qui bloque, et **dis-lui d'en parler à la personne qui lui a fourni
l'outil**. Ne modifie pas le code pour contourner.

---

## Où trouver le reste

| Fichier | Contenu |
|---|---|
| `INSTALLATION.md` | La même installation, mais à faire à la main sans Claude Code |
| `CONFIG.md` | Le détail de chaque réglage du `config.json` |
| `champs-dacces.md` | La liste des scopes Shopify à cocher |
| `CLAUDE.md` | La documentation technique complète (pour développeurs) |
| `LANCER.md` | Les commandes brutes |
