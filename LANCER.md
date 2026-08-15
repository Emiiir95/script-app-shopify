# Comment lancer

> 🆕 **Première utilisation, ou pas à l'aise avec le Terminal ?**
> Lis **[INSTALLATION.md](INSTALLATION.md)** — il suffit de double-cliquer
> `Lancer.command`, tout le reste est automatique.

Les commandes ci-dessous sont la version manuelle, pour ceux qui préfèrent le
Terminal. Toutes se lancent **depuis la racine du projet** (le dossier qui
contient `main.py`).

---

## 1. Une seule fois — installer les dépendances

```bash
pip3 install -r requirements.txt
```

---

## 2. Le Backoffice (interface web pour tout configurer)

```bash
python3 backoffice/server.py
```

Puis ouvre **http://localhost:4747** dans ton navigateur.

- Tu y règles tes boutiques et toutes les fonctionnalités.
- Sur une fonctionnalité, le bouton **« Lancer cette fonctionnalité »** ouvre un Terminal
  qui exécute **directement** cette feature sur la **boutique sélectionnée en haut** —
  pas besoin de refaire le menu. (⚠ pense à **Enregistrer** avant de lancer.)
- La page **📊 Activité** montre en direct ce qui se passe.

Pour l'arrêter : `Ctrl+C` dans le Terminal.

---

## 3. Le programme (pour lancer une fonctionnalité)

```bash
python3 main.py
```

1. Choisis la **boutique**.
2. Choisis la **fonctionnalité** (0 à 11).
3. Réponds aux questions (souvent `yes` pour valider).

Pour quitter : tape `q`.

Mode direct, sans passer par le menu :

```bash
python3 main.py --store <dossier-boutique> --feature <numéro>
```

---

## En cas de souci

- **Le style ne s'affiche pas / rien ne change** → recharge la page avec `Cmd+Shift+R`.
- **`command not found: python3`** → essaie `python` à la place, ou installe Python
  depuis https://www.python.org/downloads/
- Les logs de tout ce qui tourne sont dans `logs/app.log`.
