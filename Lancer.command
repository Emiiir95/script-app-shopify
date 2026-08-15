#!/bin/bash
#
# Lancer.command — démarre le backoffice (macOS, double-clic).
#
# Ce script est fait pour être lancé par quelqu'un qui n'a pas d'outils de dev :
#   1. il vérifie que Python 3 est présent,
#   2. il crée un environnement isolé (.venv) et installe les dépendances,
#   3. il démarre le backoffice et ouvre http://localhost:4747 dans le navigateur.
#
# Rien n'est installé ailleurs que dans ce dossier. Pour tout supprimer,
# il suffit de jeter le dossier à la corbeille.

cd "$(dirname "$0")" || exit 1

PORT=4747
VENV=".venv"

echo "============================================================"
echo "  Shopify Automation — démarrage"
echo "============================================================"
echo

# ── 1. Python 3 ───────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  echo "❌ Python 3 n'est pas installé sur cet ordinateur."
  echo
  echo "   Installe-le en 2 minutes :"
  echo "   → https://www.python.org/downloads/  (bouton jaune \"Download Python\")"
  echo "   Ouvre le fichier téléchargé, clique Continuer jusqu'au bout,"
  echo "   puis relance ce Lancer.command."
  echo
  read -r -p "Appuie sur Entrée pour fermer cette fenêtre."
  exit 1
fi

# ── 2. Environnement isolé + dépendances ──────────────────────────────────────
if [ ! -d "$VENV" ]; then
  echo "→ Première installation (une seule fois, ~1 minute)…"
  if ! python3 -m venv "$VENV"; then
    echo "❌ Impossible de créer l'environnement Python."
    read -r -p "Appuie sur Entrée pour fermer cette fenêtre."
    exit 1
  fi
fi

PY="$VENV/bin/python"

echo "→ Vérification des dépendances…"
if ! "$PY" -m pip install --quiet --upgrade pip >/dev/null 2>&1; then
  echo "   (mise à jour de pip ignorée)"
fi
if ! "$PY" -m pip install --quiet -r requirements.txt; then
  echo "❌ L'installation des dépendances a échoué."
  echo "   Vérifie que tu es connecté à Internet, puis relance."
  read -r -p "Appuie sur Entrée pour fermer cette fenêtre."
  exit 1
fi

# ── 3. Le backoffice tourne-t-il déjà ? ───────────────────────────────────────
if curl -s -o /dev/null "http://localhost:$PORT"; then
  echo
  echo "ℹ️  Le backoffice tourne déjà (une autre fenêtre est ouverte)."
  echo "   Ouverture de http://localhost:$PORT dans le navigateur…"
  open "http://localhost:$PORT"
  echo
  read -r -p "Appuie sur Entrée pour fermer cette fenêtre."
  exit 0
fi

# ── 4. Ouverture du navigateur dès que le serveur répond ──────────────────────
(
  for _ in $(seq 1 40); do
    if curl -s -o /dev/null "http://localhost:$PORT"; then
      open "http://localhost:$PORT"
      exit 0
    fi
    sleep 0.5
  done
) &

# ── 5. Backoffice ─────────────────────────────────────────────────────────────
echo
echo "→ Backoffice en cours de démarrage sur http://localhost:$PORT"
echo "   Laisse cette fenêtre OUVERTE tant que tu utilises l'outil."
echo "   Pour arrêter : Ctrl+C, ou ferme simplement cette fenêtre."
echo

"$PY" backoffice/server.py

echo
read -r -p "Backoffice arrêté. Appuie sur Entrée pour fermer cette fenêtre."
