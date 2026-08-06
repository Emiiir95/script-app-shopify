# Comment lancer

## 1. Une seule fois — installer les dépendances

```bash
pip install requests openai tqdm
```

---

## 2. Le Backoffice (interface web pour tout configurer)

```bash
cd "/Users/emirsen/Desktop/app/script/GMC - shopify automatisé/backoffice"
python3 server.py
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
cd "/Users/emirsen/Desktop/app/script/GMC - shopify automatisé"
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
