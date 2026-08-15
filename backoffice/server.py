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

# Permet d'importer le module `shopify` du projet (fetch live des collections).
sys.path.insert(0, PROJECT_ROOT)

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


def fetch_shopify_menu_resources(folder):
    """
    Récupère EN DIRECT collections + pages + blogs de la boutique Shopify (GraphQL),
    pour peupler les listes déroulantes du constructeur de menus.

    Retourne { collections: [...], pages: [...], blogs: [...] } où chaque item = {handle, title}.
    Résilient : si un type échoue (scope manquant…), il renvoie [] sans casser les autres.
    """
    from shopify.client import shopify_headers, shopify_base_url, graphql_request, SHOPIFY_API_VERSION
    cfg      = read_config(folder)
    base_url = shopify_base_url(cfg["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(cfg["access_token"])

    def paginate(root):
        query = (
            "query($cursor: String) { " + root + "(first: 250, after: $cursor) { "
            "nodes { handle title } pageInfo { hasNextPage endCursor } } }"
        )
        out, cursor = [], None
        while True:
            data = graphql_request(base_url, headers, query, {"cursor": cursor})
            node = data.get("data", {}).get(root, {})
            for n in node.get("nodes", []):
                out.append({"handle": n["handle"], "title": n.get("title", "")})
            page = node.get("pageInfo", {})
            if not page.get("hasNextPage"):
                break
            cursor = page["endCursor"]
        out.sort(key=lambda c: (c["title"] or "").lower())
        return out

    def safe(root):
        try:
            return paginate(root)
        except Exception:
            return []

    return {
        "collections": safe("collections"),
        "pages":       safe("pages"),
        "blogs":       safe("blogs"),
    }


def _menu_item_to_config(item):
    """
    Convertit un MenuItem GraphQL Shopify au format attendu par l'éditeur de l'app.

    Shopify référence les ressources par GID (resourceId), mais expose aussi une
    `url` storefront (ex: "/collections/mon-handle") — on en extrait le handle,
    ce qui évite toute résolution de GID. Récursif sur les sous-items (max 3 niveaux).
    """
    t   = (item.get("type") or "").upper()
    url = item.get("url") or ""
    tail = url.rstrip("/").split("/")[-1].split("?")[0] if url else ""

    out = {"title": item.get("title", ""), "type": t}
    if t in ("COLLECTION", "PAGE", "BLOG", "ARTICLE", "PRODUCT"):
        out["handle"] = tail
    elif t == "HTTP":
        out["url"] = url
    elif t == "SHOP_POLICY":
        out["policy_type"] = tail.upper().replace("-", "_") if tail else ""
    # FRONTPAGE / CATALOG / SEARCH : aucun champ ressource

    children = item.get("items") or []
    if children:
        out["items"] = [_menu_item_to_config(c) for c in children]
    return out


def fetch_shopify_menus(folder):
    """
    Récupère la structure RÉELLE des menus de navigation de la boutique (GraphQL)
    et la renvoie au format de l'éditeur de l'app : { menus: [ {title, handle, items:[...] } ] }.

    Permet au bouton « Importer mes menus Shopify » de refléter dans l'app ce qui
    existe réellement côté Shopify. Nécessite le scope read_online_store_navigation.
    """
    from shopify.client import shopify_headers, shopify_base_url, graphql_request, SHOPIFY_API_VERSION
    cfg      = read_config(folder)
    base_url = shopify_base_url(cfg["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(cfg["access_token"])

    item = "title type url"
    query = (
        "{ menus(first: 50) { nodes { handle title items { " + item +
        " items { " + item + " items { " + item + " } } } } } }"
    )
    data  = graphql_request(base_url, headers, query, {})
    nodes = data.get("data", {}).get("menus", {}).get("nodes", []) or []

    menus = []
    for m in nodes:
        menus.append({
            "title":  m.get("title", ""),
            "handle": m.get("handle", ""),
            "items":  [_menu_item_to_config(it) for it in (m.get("items") or [])],
        })
    return {"menus": menus}


def _load_openai_key():
    """Lit OPENAI_API_KEY depuis le .env racine (partagé). '' si absent."""
    env_path = os.path.join(PROJECT_ROOT, ".env")
    if not os.path.isfile(env_path):
        return ""
    with open(env_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("OPENAI_API_KEY") and "=" in line:
                return line.partition("=")[2].strip()
    return ""


def _mask_key(key):
    """Masque une clé pour l'affichage : 'sk-...abcd' (jamais renvoyée en clair)."""
    key = (key or "").strip()
    if len(key) <= 8:
        return "•" * len(key)
    return f"{key[:3]}…{key[-4:]}"


def get_openai_key_status():
    """État de la clé OpenAI pour le backoffice (sans jamais renvoyer la clé en clair)."""
    key = _load_openai_key()
    return {"set": bool(key), "masked": _mask_key(key) if key else ""}


def save_openai_key(key):
    """
    Écrit/met à jour OPENAI_API_KEY dans le .env racine, en préservant les autres
    lignes. Permet à un non-dev de saisir sa clé depuis le navigateur, sans éditer
    de fichier caché ni ouvrir de terminal.
    """
    key = (key or "").strip()
    if not key:
        raise ValueError("La clé OpenAI est vide.")
    if not key.startswith("sk-"):
        raise ValueError("Une clé OpenAI commence par « sk- ». Vérifie le copier-coller.")

    env_path = os.path.join(PROJECT_ROOT, ".env")
    lines, found = [], False
    if os.path.isfile(env_path):
        with open(env_path, encoding="utf-8") as f:
            for line in f:
                if line.strip().startswith("OPENAI_API_KEY") and "=" in line:
                    lines.append(f"OPENAI_API_KEY={key}\n")
                    found = True
                else:
                    lines.append(line if line.endswith("\n") else line + "\n")
    if not found:
        lines.append(f"OPENAI_API_KEY={key}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    try:
        os.chmod(env_path, 0o600)   # lecture/écriture propriétaire uniquement
    except OSError:
        pass
    return get_openai_key_status()


def resolve_categories(folder, niches):
    """
    Bouton « Récupérer les catégories » : télécharge la taxonomie Shopify publique (FR),
    et pour chaque niche choisit automatiquement la catégorie la plus proche (IA si une
    clé OpenAI est dispo, sinon lexical). Générique : marche pour toute boutique.

    Args:
        folder : dossier de la boutique
        niches : liste de niches (str). Si vide, retombe sur seo_boost.niches du config.

    Returns:
        dict { rules: [ {match, name, search, gid, fullName, found, via, niche} ], ai: bool }
    """
    from utils.taxonomy import load_taxonomy, suggest_categories

    cfg = read_config(folder)
    if not niches:
        niches = (cfg.get("seo_boost", {}) or {}).get("niches", []) or []
    niches = [n for n in (niches or []) if (n or "").strip()]
    if not niches:
        raise ValueError("Aucune niche fournie — ajoute tes niches (ou renseigne seo_boost.niches).")

    openai_key = _load_openai_key()
    entries    = load_taxonomy()
    rules      = suggest_categories(niches, openai_key=openai_key, entries=entries)
    return {"rules": rules, "ai": bool(openai_key)}


def list_store_backups(folder):
    """Liste les snapshots (retour en arrière) disponibles pour une boutique."""
    from utils.backup import list_snapshots
    store_path = _safe_store_path(folder)
    return {"backups": list_snapshots(store_path)}


def list_generated_features(folder):
    """Indique quelles features ont déjà généré (archive présente) → pour l'ordre."""
    from utils.archive import list_generated
    store_path = _safe_store_path(folder)
    feats = ["seo_boost", "fiche_produit", "reviews", "fond_studio"]
    return {"generated": {f: bool(list_generated(store_path, f)) for f in feats}}


def rollback_snapshot(folder, filename=None):
    """
    Restaure un snapshot produit dans Shopify (retour en arrière).
    Réécrit les champs sauvegardés (title/handle/body_html…) via PUT, par ID produit.

    Args:
        folder   : dossier de la boutique
        filename : nom du snapshot (défaut = le plus récent)

    Returns:
        dict { restored, failed, file, created_at, count }
    """
    from shopify.client import (
        shopify_headers, shopify_base_url, shopify_put, SHOPIFY_API_VERSION,
    )
    from shopify.products import (
        set_product_metafield, fetch_all_product_metafields, delete_product_metafield,
    )
    from utils.backup import load_snapshot, latest_snapshot_file

    store_path = _safe_store_path(folder)
    if not filename:
        filename = latest_snapshot_file(store_path)
    if not filename:
        raise ValueError("Aucune sauvegarde disponible pour cette boutique.")

    snap     = load_snapshot(store_path, filename)   # basename-safe côté util
    fields   = [f for f in snap.get("fields", []) if f != "_metafields_backup"]
    cfg      = read_config(folder)
    base_url = shopify_base_url(cfg["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(cfg["access_token"])

    restored, failed = 0, 0
    for p in snap.get("products", []):
        pid = p.get("id")
        if not pid:
            continue
        # 1. Champs produit simples (title / handle / body_html)
        payload = {"product": {"id": pid}}
        for f in fields:
            if f in p:
                payload["product"][f] = p[f]
        try:
            shopify_put(f"{base_url}/products/{pid}.json", headers, payload)
            restored += 1
        except Exception:
            failed += 1
            continue

        # 2. Metafields écrits par SEO Boost : restaure l'ancienne valeur, ou supprime
        #    ceux qui n'existaient pas avant (value == None).
        mf_backup = p.get("_metafields_backup") or []
        if mf_backup:
            try:
                current = {
                    (m.get("namespace"), m.get("key")): m
                    for m in fetch_all_product_metafields(pid, base_url, headers)
                }
            except Exception:
                current = {}
            for entry in mf_backup:
                ns, key   = entry.get("namespace"), entry.get("key")
                old_value = entry.get("value")
                try:
                    if old_value is None:
                        m = current.get((ns, key))
                        if m and m.get("id"):
                            delete_product_metafield(m["id"], base_url, headers)
                    else:
                        set_product_metafield(
                            pid, ns, key, old_value,
                            entry.get("type") or "single_line_text_field",
                            base_url, headers,
                        )
                except Exception:
                    pass

    return {
        "restored":   restored,
        "failed":     failed,
        "file":       os.path.basename(filename),
        "created_at": snap.get("created_at"),
        "count":      len(snap.get("products", [])),
    }


def rollback_feature(folder, feature):
    """Retour en arrière Fiche Produit / Reviews : supprime les metafields écrits."""
    from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
    from features.reset.clearer import clear_feature_metafields
    _safe_store_path(folder)                     # valide le dossier
    cfg      = read_config(folder)
    base_url = shopify_base_url(cfg["store_url"], SHOPIFY_API_VERSION)
    headers  = shopify_headers(cfg["access_token"])
    return clear_feature_metafields(feature, base_url, headers)


def push_saved_data(folder, features=None):
    """Repousse vers Shopify la data déjà générée (CSV d'aperçu), sans OpenAI."""
    from shopify.client import shopify_headers, shopify_base_url, SHOPIFY_API_VERSION
    from features.push_saved.pusher import push_all
    store_path = _safe_store_path(folder)
    cfg        = read_config(folder)
    base_url   = shopify_base_url(cfg["store_url"], SHOPIFY_API_VERSION)
    headers    = shopify_headers(cfg["access_token"])
    feats      = tuple(features) if features else ("seo_boost", "reviews")
    return push_all(store_path, base_url, headers, feats)


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
            elif path == "/api/shopify/menu-resources":
                folder = (qs.get("store") or [""])[0]
                self._send_json(fetch_shopify_menu_resources(folder))
            elif path == "/api/shopify/menus":
                folder = (qs.get("store") or [""])[0]
                self._send_json(fetch_shopify_menus(folder))
            elif path == "/api/backups":
                folder = (qs.get("store") or [""])[0]
                self._send_json(list_store_backups(folder))
            elif path == "/api/openai-key":
                self._send_json(get_openai_key_status())
            elif path == "/api/generated":
                folder = (qs.get("store") or [""])[0]
                self._send_json(list_generated_features(folder))
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
            elif path == "/api/rollback":
                body = self._read_body()
                self._send_json(rollback_snapshot(body.get("store"), body.get("file")))
            elif path == "/api/push-saved":
                body = self._read_body()
                self._send_json(push_saved_data(body.get("store"), body.get("features")))
            elif path == "/api/openai-key":
                body = self._read_body()
                self._send_json(save_openai_key(body.get("key")))
            elif path == "/api/rollback-feature":
                body = self._read_body()
                self._send_json(rollback_feature(body.get("store"), body.get("feature")))
            elif path == "/api/shopify/resolve-categories":
                body = self._read_body()
                self._send_json(resolve_categories(body.get("store"), body.get("niches")))
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
