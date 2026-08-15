#!/bin/bash
# Lance le projet FRONT (maquettes statiques du dossier front/) sur http://localhost:8080
# Double-clique ce fichier dans le Finder, ou lance-le depuis le terminal : ./front.command

cd "$(dirname "$0")" || exit 1

PORT=8080
PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "❌ Python 3 introuvable. Installe-le puis relance."
  exit 1
fi

echo "============================================================"
echo "  FRONT — maquettes statiques (dossier front/)"
echo "  → http://localhost:$PORT           (Dashboard)"
echo "  → http://localhost:$PORT/store.html (Store Manager)"
echo "  Ctrl+C pour arrêter"
echo "============================================================"

# Ouvre le navigateur juste après le démarrage du serveur
( sleep 1; open "http://localhost:$PORT" 2>/dev/null ) &

exec "$PY" -m http.server "$PORT" --directory front
