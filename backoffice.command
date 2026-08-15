#!/bin/bash
# Lance le BACKOFFICE (éditeur de config web : menus, SEO, politiques…) sur http://localhost:4747
# Double-clique ce fichier dans le Finder, ou lance-le depuis le terminal : ./backoffice.command

cd "$(dirname "$0")" || exit 1

PY="$(command -v python3 || command -v python)"
if [ -z "$PY" ]; then
  echo "❌ Python 3 introuvable. Installe-le puis relance."
  exit 1
fi

# Ouvre le navigateur juste après le démarrage du serveur
( sleep 1; open "http://localhost:4747" 2>/dev/null ) &

exec "$PY" backoffice/server.py
