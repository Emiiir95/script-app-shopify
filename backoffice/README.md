# Backoffice — Shopify Automation

Interface web **locale** pour configurer toutes les fonctionnalités du projet.
Zéro dépendance (bibliothèque standard Python uniquement).

## Lancer

```bash
cd backoffice
python3 server.py
```

Puis ouvrir **http://localhost:4747**

## Ce que ça fait

- **Menu à gauche** : les 11 fonctionnalités + la page « Boutique » (identifiants).
- **Sélecteur de boutique** en haut : bascule entre les dossiers de `stores/`.
- **« + Nouvelle boutique »** : clone `stores/_template/` (config + fichiers de
  contexte + politiques + keywords) dans un nouveau dossier et pré-remplit
  nom / URL / access token. Le nom est transformé en slug de dossier
  (ex : « Mon Atelier Déco » → `mon-atelier-deco`).
- **Chaque page** affiche tous les paramètres de la fonctionnalité et les écrit
  directement dans le vrai `config.json` de la boutique (les mêmes clés que lisent
  les runners Python). C'est donc **réellement relié** à la logique du projet.
- Les fonctionnalités à base de fichiers (Reviews, Fiche Produit, Politiques)
  permettent aussi d'éditer les fichiers de contexte (`.md`, templates).

## Exécution des features

Les runners du projet sont **interactifs** (ils posent des questions oui/non,
choix de statut produit, etc.) : impossible de les piloter proprement depuis un
serveur web. Le bouton **« Lancer dans le Terminal »** ouvre donc le vrai CLI
interactif (`python main.py`) — sur macOS il ouvre un nouveau Terminal ;
ailleurs il affiche la commande à copier.

**Workflow type :** configurer/valider les paramètres ici → cliquer « Lancer » →
choisir la boutique + la feature dans le Terminal.

## Sécurité

- Écoute uniquement sur `127.0.0.1` (localhost).
- Les accès fichiers sont restreints au dossier `stores/{boutique}/`
  (protection contre le path traversal).
- ⚠️ Le backoffice édite des `config.json` contenant les **access tokens Shopify** :
  ne pas l'exposer sur un réseau.
