#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
server.py — Backoffice local pour Shopify Automation.

Serveur HTTP minimaliste (bibliothèque standard uniquement — aucune dépendance)
qui expose une interface web pour éditer les config.json des boutiques et les
fichiers de contexte (reviews/*.md, reassurance.md, politiques/*.html).

Le backoffice est un ÉDITEUR DE CONFIGURATION : il écrit exactement les clés que
les runners lisent. Il ne lance pas les features directement (les runners sont
interactifs) — le bouton « Lancer » ouvre le vrai CLI `python main.py` dans le
Terminal.

Lancement :
    cd backoffice
    python3 server.py
    → http://localhost:4747
"""

import json
import os
import re
import shlex
import shutil
import subprocess
import sys
import unicodedata
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs

PORT         = 4747
BACKOFFICE   = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(BACKOFFICE)
STORES_DIR   = os.path.join(PROJECT_ROOT, "stores")
STATIC_DIR   = os.path.join(BACKOFFICE, "static")
LOG_FILE     = os.path.join(PROJECT_ROOT, "logs", "app.log")

_CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js":   "application/javascript; charset=utf-8",
    ".css":  "text/css; charset=utf-8",
    ".json": "application/json; charset=utf-8",
}


# ── Helpers stores / fichiers ─────────────────────────────────────────────────

def list_stores():
    """Retourne les boutiques valides : dossiers dans stores/ avec un config.json."""
    stores = []
    if not os.path.isdir(STORES_DIR):
        return stores
    for entry in sorted(os.listdir(STORES_DIR)):
        if entry.startswith("_") or entry.startswith("."):
            continue
        config_path = os.path.join(STORES_DIR, entry, "config.json")
        if os.path.isfile(config_path):
            try:
                with open(config_path, encoding="utf-8") as f:
                    cfg = json.load(f)
            except Exception:
                cfg = {}
            stores.append({
                "folder":    entry,
                "name":      cfg.get("name", entry),
                "store_url": cfg.get("store_url", ""),
            })
    return stores


def _safe_store_path(folder, *parts):
    """
    Construit un chemin dans stores/{folder}/... en refusant toute évasion
    du dossier de la boutique (path traversal).
    """
    base = os.path.realpath(os.path.join(STORES_DIR, folder))
    stores_root = os.path.realpath(STORES_DIR)
    if not base.startswith(stores_root + os.sep):
        raise ValueError("Dossier boutique invalide")
    target = os.path.realpath(os.path.join(base, *parts))
    if not (target == base or target.startswith(base + os.sep)):
        raise ValueError("Chemin hors de la boutique")
    return target


def read_config(folder):
    path = _safe_store_path(folder, "config.json")
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_config(folder, data):
    path = _safe_store_path(folder, "config.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def read_store_file(folder, relname):
    path = _safe_store_path(folder, relname)
    if not os.path.isfile(path):
        return ""
    with open(path, encoding="utf-8") as f:
        return f.read()


def write_store_file(folder, relname, content):
    path = _safe_store_path(folder, relname)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def slugify(name):
    """Transforme un nom en slug de dossier (ex: 'L'Atelier Veilleuse' → 'l-atelier-veilleuse')."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_name).strip("-").lower()
    return slug


def create_store(name, store_url, access_token):
    """
    Crée une nouvelle boutique en clonant stores/_template/.

    Renseigne name / store_url / access_token dans le config.json copié ;
    le reste du template (placeholders, fichiers de contexte) est conservé.

    Returns:
        str : le folder de la boutique créée.
    """
    name = (name or "").strip()
    if not name:
        raise ValueError("Le nom de la boutique est requis")

    folder = slugify(name)
    if not folder:
        raise ValueError("Nom invalide — impossible de générer un dossier")

    template_dir = os.path.join(STORES_DIR, "_template")
    if not os.path.isdir(template_dir):
        raise ValueError("Template introuvable : stores/_template/")

    target = _safe_store_path(folder)
    if os.path.exists(target):
        raise ValueError(f"La boutique « {folder} » existe déjà")

    shutil.copytree(template_dir, target)

    # Renseigne les identifiants dans le config.json copié
    cfg = read_config(folder)
    cfg["name"]         = name
    cfg["store_url"]    = (store_url or "").strip()
    cfg["access_token"] = (access_token or "").strip()
    write_config(folder, cfg)

    return folder


def read_log_tail(n_lines=300):
    """Retourne les n dernières lignes de logs/app.log (lecture efficace de la fin)."""
    if not os.path.isfile(LOG_FILE):
        return ""
    with open(LOG_FILE, "rb") as f:
        f.seek(0, os.SEEK_END)
        size  = f.tell()
        block = min(size, 65536)             # ne lit que les derniers 64 Ko
        f.seek(size - block)
        data = f.read().decode("utf-8", "replace")
    lines = data.splitlines()
    return "\n".join(lines[-n_lines:])


def open_terminal(store=None, feature=None):
    """
    Ouvre le CLI dans un nouveau Terminal (macOS).
    Si store + feature sont fournis, lance directement cette feature sur cette
    boutique (main.py --store <folder> --feature <id>) — sinon menu interactif.
    """
    if sys.platform != "darwin":
        return False, f"Ouverture auto du Terminal supportée sur macOS uniquement. Commande : cd '{PROJECT_ROOT}' && python3 main.py"
    py = sys.executable or "python3"
    # Commande shell : chemins entre guillemets SIMPLES (shlex.quote) pour ne pas
    # entrer en conflit avec les guillemets doubles de la chaîne AppleScript.
    extra = ""
    if store and feature:
        extra = f" --store {shlex.quote(store)} --feature {shlex.quote(feature)}"
    cmd = f"cd {shlex.quote(PROJECT_ROOT)} && {shlex.quote(py)} main.py{extra}"
    # Échappement pour AppleScript (chaîne entre guillemets doubles) : backslash puis guillemet.
    cmd_as = cmd.replace("\\", "\\\\").replace('"', '\\"')
    script = f'tell application "Terminal"\n  activate\n  do script "{cmd_as}"\nend tell'
    try:
        subprocess.run(["osascript", "-e", script], check=True)
        return True, "Terminal ouvert — le CLI interactif est lancé."
    except Exception as e:
        return False, f"Impossible d'ouvrir le Terminal : {e}"


# ── Handler HTTP ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def log_message(self, *args):
        pass  # silence les logs par requête

    # -- utils réponse --
    def _send_json(self, obj, status=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_error(self, msg, status=400):
        self._send_json({"error": msg}, status)

    def _read_body(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        if not length:
            return {}
        raw = self.rfile.read(length)
        return json.loads(raw.decode("utf-8"))

    def _serve_static(self, path):
        if path in ("/", ""):
            rel = "index.html"
        elif path.startswith("/static/"):
            rel = path[len("/static/"):]     # /static/style.css → style.css (STATIC_DIR se termine déjà par /static)
        else:
            rel = path.lstrip("/")
        full = os.path.realpath(os.path.join(STATIC_DIR, rel))
        if not full.startswith(os.path.realpath(STATIC_DIR)) or not os.path.isfile(full):
            self._send_error("Not found", 404)
            return
        ext = os.path.splitext(full)[1]
        ctype = _CONTENT_TYPES.get(ext, "application/octet-stream")
        with open(full, "rb") as f:
            body = f.read()
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store, must-revalidate")  # outil de dev : toujours servir la dernière version
        self.end_headers()
        self.wfile.write(body)

    # -- GET --
    def do_GET(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        try:
            if path == "/api/stores":
                self._send_json({"stores": list_stores()})
            elif path == "/api/store":
                folder = (qs.get("folder") or [""])[0]
                self._send_json({"config": read_config(folder)})
            elif path == "/api/file":
                folder = (qs.get("store") or [""])[0]
                name   = (qs.get("name") or [""])[0]
                self._send_json({"content": read_store_file(folder, name)})
            elif path == "/api/logs":
                try:
                    n = int((qs.get("lines") or ["300"])[0])
                except ValueError:
                    n = 300
                self._send_json({"content": read_log_tail(n)})
            elif path.startswith("/api/"):
                self._send_error("Endpoint inconnu", 404)
            else:
                self._serve_static(path)
        except Exception as e:
            self._send_error(str(e), 400)

    # -- POST --
    def do_POST(self):
        parsed = urlparse(self.path)
        path   = parsed.path
        qs     = parse_qs(parsed.query)

        try:
            if path == "/api/store":
                folder = (qs.get("folder") or [""])[0]
                body   = self._read_body()
                write_config(folder, body.get("config", {}))
                self._send_json({"ok": True})
            elif path == "/api/file":
                folder = (qs.get("store") or [""])[0]
                name   = (qs.get("name") or [""])[0]
                body   = self._read_body()
                write_store_file(folder, name, body.get("content", ""))
                self._send_json({"ok": True})
            elif path == "/api/store/create":
                body   = self._read_body()
                folder = create_store(
                    body.get("name", ""),
                    body.get("store_url", ""),
                    body.get("access_token", ""),
                )
                self._send_json({"ok": True, "folder": folder})
            elif path == "/api/run":
                body    = self._read_body()
                ok, msg = open_terminal(body.get("store"), body.get("feature"))
                self._send_json({"ok": ok, "message": msg})
            else:
                self._send_error("Endpoint inconnu", 404)
        except Exception as e:
            self._send_error(str(e), 400)


def main():
    os.chdir(BACKOFFICE)
    server = ThreadingHTTPServer(("127.0.0.1", PORT), Handler)
    print("=" * 60)
    print("  Backoffice Shopify Automation")
    print(f"  → http://localhost:{PORT}")
    print(f"  Boutiques : {STORES_DIR}")
    print("  Ctrl+C pour arrêter")
    print("=" * 60)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du backoffice.")
        server.shutdown()


if __name__ == "__main__":
    main()
