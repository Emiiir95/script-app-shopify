#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
lock.py — Verrou inter-processus par boutique.

Chaque feature tourne dans son propre processus (Terminal). Si plusieurs sont
lancées en même temps sur la même boutique, leurs écritures Shopify se
chevauchent → conflits + saturation du rate limit (429) + produits sautés.

Ce verrou (fichier .inject.lock dans le dossier de la boutique) sérialise la
PHASE D'INJECTION : une seule feature écrit à la fois, les autres attendent leur
tour. Résultat : on peut tout lancer d'un coup, tout se termine proprement.

Un verrou périmé (processus mort ou plus vieux que STALE_SECONDS) est volé
automatiquement pour ne jamais bloquer indéfiniment.
"""

import json
import os
import time

from utils.logger import log

LOCK_NAME     = ".inject.lock"
STALE_SECONDS = 1800   # 30 min : au-delà, le verrou est considéré abandonné
POLL_SECONDS  = 2.0    # fréquence de vérification pendant l'attente


def _lock_path(store_path):
    return os.path.join(store_path, LOCK_NAME)


def _read_lock(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _pid_alive(pid):
    """True si le processus `pid` tourne encore (best effort, POSIX)."""
    if not pid:
        return False
    try:
        os.kill(int(pid), 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True          # existe mais appartient à un autre user
    except (OSError, ValueError):
        return False


class StoreLock:
    """
    Verrou fichier par boutique. À utiliser autour de la phase d'injection :

        lock = StoreLock(store_path, "seo_boost")
        lock.acquire(wait_message="  ⏳ Une autre feature écrit — attente...")
        try:
            ...injection...
        finally:
            lock.release()

    Ou en context manager : `with StoreLock(store_path, "seo_boost"):`.
    """

    def __init__(self, store_path, feature, poll=POLL_SECONDS, stale_seconds=STALE_SECONDS):
        self.path          = _lock_path(store_path)
        self.feature       = feature
        self.poll          = poll
        self.stale_seconds = stale_seconds
        self.acquired      = False

    def acquire(self, wait_message=None):
        """Bloque jusqu'à obtenir le verrou. Affiche `wait_message` une fois si attente."""
        warned = False
        while True:
            try:
                fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
                os.write(fd, json.dumps({
                    "feature": self.feature, "pid": os.getpid(), "ts": time.time(),
                }).encode("utf-8"))
                os.close(fd)
                self.acquired = True
                log(f"Verrou boutique acquis — {self.feature}")
                return
            except FileExistsError:
                info = _read_lock(self.path)
                too_old   = info is None or (time.time() - info.get("ts", 0)) > self.stale_seconds
                dead_proc = info is not None and not _pid_alive(info.get("pid"))
                if info is None or too_old or dead_proc:
                    # Verrou périmé → on le vole
                    log(f"Verrou boutique périmé volé par {self.feature}", "warning")
                    try:
                        os.remove(self.path)
                    except OSError:
                        pass
                    continue
                if wait_message and not warned:
                    print(wait_message.format(feature=info.get("feature", "?")))
                    warned = True
                log(f"{self.feature} attend le verrou (tenu par {info.get('feature')})")
                time.sleep(self.poll)

    def release(self):
        if self.acquired:
            try:
                os.remove(self.path)
            except OSError:
                pass
            self.acquired = False
            log(f"Verrou boutique libéré — {self.feature}")

    def __enter__(self):
        self.acquire(wait_message="  ⏳ Une autre feature ({feature}) écrit sur Shopify — attente de son tour...")
        return self

    def __exit__(self, *exc):
        self.release()
        return False
