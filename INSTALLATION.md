# Installation (Mac) — guide pas à pas

Ce guide s'adresse à quelqu'un qui **n'est pas développeur**. Aucun outil
particulier n'est nécessaire : ni VSCode, ni Git, ni ligne de commande.
Compte 10 minutes la première fois.

---

## Étape 1 — Installer Python (une seule fois)

L'outil est écrit en Python. Pour savoir s'il est déjà installé :

1. Ouvre **Terminal** (⌘ + espace, tape `Terminal`, Entrée).
2. Tape `python3 --version` puis Entrée.

- Si ça affiche `Python 3.x.x` → c'est bon, passe à l'étape 2.
- Si ça dit `command not found` → télécharge Python sur
  **https://www.python.org/downloads/** (gros bouton jaune), ouvre le fichier
  téléchargé et clique « Continuer » jusqu'au bout.

---

## Étape 2 — Télécharger le projet

1. Va sur **https://github.com/Emiiir95/script-app-shopify**
2. Bouton vert **`Code`** → **`Download ZIP`**
3. Double-clique le ZIP téléchargé pour le décompresser.
4. Déplace le dossier obtenu (`script-app-shopify-main`) là où tu veux le garder
   — par exemple sur le **Bureau**. Ne le laisse pas dans « Téléchargements ».

---

## Étape 3 — Lancer

Double-clique le fichier **`Lancer.command`** dans le dossier.

> ⚠️ **Au premier lancement, macOS va probablement refuser d'ouvrir le fichier**
> (« impossible de vérifier le développeur »). C'est normal pour un fichier venu
> d'un ZIP téléchargé. Solution :
> **clic droit** sur `Lancer.command` → **Ouvrir** → bouton **Ouvrir** dans la
> fenêtre d'alerte. À faire une seule fois ; ensuite le double-clic suffit.
>
> Si macOS refuse toujours, ouvre Terminal et colle cette ligne (en remplaçant
> le chemin par ton dossier — tu peux le glisser-déposer depuis le Finder) :
> ```
> xattr -dr com.apple.quarantine "/Users/toi/Desktop/script-app-shopify-main"
> ```

Une fenêtre Terminal s'ouvre, installe ce qu'il faut (~1 minute la première
fois), puis **ton navigateur s'ouvre tout seul sur le backoffice**.

**Laisse la fenêtre Terminal ouverte** tant que tu utilises l'outil. Pour
arrêter : ferme-la, ou fais `Ctrl+C` dedans.

---

## Étape 4 — Configurer (dans le navigateur)

Tout se fait depuis le backoffice, il n'y a plus rien à taper.

### 4.1 — La clé OpenAI

L'outil génère des textes avec l'IA, il lui faut une clé OpenAI.
Crée-la sur **https://platform.openai.com/api-keys** (elle commence par `sk-`),
puis colle-la dans le champ prévu dans le backoffice. Elle est partagée par
toutes les boutiques et enregistrée dans un fichier `.env` local.

> 💡 Une clé OpenAI est **payante à l'usage**. Pense à mettre une limite de
> dépense mensuelle dans les réglages de ton compte OpenAI.

### 4.2 — Ta boutique Shopify

Dans le backoffice, crée une nouvelle boutique. Il te faudra deux informations :

| Info | Où la trouver |
|---|---|
| **URL de la boutique** (`xxx.myshopify.com`) | Admin Shopify → barre d'adresse |
| **Token d'accès** (commence par `shpat_`) | Admin Shopify → Paramètres → Applications et canaux de vente → Développer des applications → Créer une application → Configurer les scopes → Installer → révéler le token Admin API |

Les scopes (permissions) à cocher sont listés dans **`champs-dacces.md`**.

> 🔒 Le token et la clé OpenAI restent **uniquement sur ton ordinateur**. Ils ne
> sont jamais envoyés sur GitHub (le `.gitignore` les exclut).

### 4.3 — Régler les fonctionnalités

Chaque fonctionnalité (SEO Boost, Fiche Produit, Reviews…) a ses réglages dans
le backoffice. **Pense à cliquer « Enregistrer » avant de lancer.**
Le détail de chaque réglage est dans **`CONFIG.md`**.

---

## Étape 5 — Faire tourner une fonctionnalité

Dans le backoffice, sélectionne la boutique en haut, va sur une fonctionnalité,
clique **« Lancer cette fonctionnalité »**. Une fenêtre Terminal s'ouvre et
exécute le traitement ; réponds aux questions posées (souvent `yes` pour
valider). La page **📊 Activité** montre ce qui se passe en direct.

> ⚠️ **Ces fonctionnalités modifient de vrais produits sur ta boutique.**
> Teste d'abord sur une boutique de développement ou sur quelques produits.

---

## Les jours suivants

Il n'y a plus rien à installer : **double-clic sur `Lancer.command`**, c'est tout.

---

## En cas de souci

| Problème | Solution |
|---|---|
| « impossible de vérifier le développeur » | Clic droit → Ouvrir (voir étape 3) |
| `command not found: python3` | Python n'est pas installé → étape 1 |
| Le navigateur ne s'ouvre pas | Va manuellement sur http://localhost:4747 |
| « Address already in use » | Le backoffice tourne déjà dans une autre fenêtre |
| La page n'affiche pas les bons styles | Recharge avec `Cmd+Shift+R` |
| Une fonctionnalité plante | Regarde le fichier `logs/app.log` |

Pour mettre à jour vers une nouvelle version : retélécharge le ZIP (étape 2).
Copie ton dossier `stores/` et ton fichier `.env` de l'ancien dossier vers le
nouveau pour conserver ta configuration.
