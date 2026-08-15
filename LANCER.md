# Comment lancer

## 1. Une seule fois — installer les dépendances

```bash
pip install requests openai tqdm
```

---

## 2. Lancer depuis la RACINE du projet (le plus simple)

Deux fichiers **double-cliquables** sont à la racine du projet. Double-clique-les
dans le Finder (ils démarrent le serveur **et ouvrent le navigateur tout seuls**),
ou lance-les depuis le terminal placé à la racine du projet :

```bash
./backoffice.command   # Backoffice — éditeur de config web  → http://localhost:4747
./front.command        # Front — maquettes statiques         → http://localhost:8080
```

> ⚠️ **Backoffice = l'interface fonctionnelle** (règle tes boutiques, menus, SEO…).
> **Front = des maquettes statiques** (Dashboard + Store Manager, sans données réelles).

Équivalent en commande brute (sans les scripts), toujours **depuis la racine** :

```bash
python3 backoffice/server.py                     # Backoffice (port 4747)
python3 -m http.server 8080 --directory front    # Front      (port 8080)
```

Pour arrêter l'un ou l'autre : `Ctrl+C` dans la fenêtre (ou ferme-la).

---

## 3. Le Backoffice en détail (interface web pour tout configurer)

Ouvre **http://localhost:4747** dans ton navigateur.

- Tu y règles tes boutiques et toutes les fonctionnalités.
- Sur une fonctionnalité, le bouton **« Lancer cette fonctionnalité »** ouvre un Terminal
  qui exécute **directement** cette feature sur la **boutique sélectionnée en haut** —
  pas besoin de refaire le menu. (⚠ pense à **Enregistrer** avant de lancer.)
- La page **📊 Activité** montre en direct ce qui se passe.

Pour l'arrêter : `Ctrl+C` dans le Terminal.

---

## 4. Le programme en ligne de commande (pour lancer une fonctionnalité)

Depuis la **racine du projet** :

```bash
python3 main.py
```

1. Choisis la **boutique**.
2. Choisis la **fonctionnalité** (0 à 10).
3. Réponds aux questions (souvent `yes` pour valider).

Pour quitter : tape `q`.

---

## En cas de souci

- **Le style ne s'affiche pas / rien ne change** → recharge la page avec `Cmd+Shift+R`.
- **`command not found: python3`** → essaie `python` à la place.
- Les logs de tout ce qui tourne sont dans `logs/app.log`.
