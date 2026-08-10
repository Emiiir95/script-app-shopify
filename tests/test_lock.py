#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tests unitaires — utils/lock.py (verrou inter-processus par boutique)."""

import json
import os
import tempfile
import time
import unittest

from utils.lock import StoreLock, _lock_path, _pid_alive, LOCK_NAME


class TestStoreLock(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()

    def _write_lock(self, feature="other", pid=None, ts=None):
        data = {"feature": feature, "pid": pid if pid is not None else os.getpid(),
                "ts": ts if ts is not None else time.time()}
        with open(_lock_path(self.tmp), "w", encoding="utf-8") as f:
            json.dump(data, f)

    def test_acquire_creates_file_release_removes(self):
        lock = StoreLock(self.tmp, "seo_boost")
        lock.acquire()
        self.assertTrue(os.path.exists(os.path.join(self.tmp, LOCK_NAME)))
        self.assertTrue(lock.acquired)
        lock.release()
        self.assertFalse(os.path.exists(os.path.join(self.tmp, LOCK_NAME)))

    def test_steals_stale_lock(self):
        # Verrou vieux de 2h → périmé → volé
        self._write_lock(feature="old", ts=time.time() - 7200)
        lock = StoreLock(self.tmp, "seo_boost", stale_seconds=1800)
        lock.acquire()                       # ne doit pas bloquer
        self.assertTrue(lock.acquired)
        info = json.load(open(_lock_path(self.tmp)))
        self.assertEqual(info["feature"], "seo_boost")

    def test_steals_dead_pid_lock(self):
        # Verrou récent mais PID mort → volé
        self._write_lock(feature="dead", pid=999999, ts=time.time())
        lock = StoreLock(self.tmp, "fond_studio")
        lock.acquire()
        self.assertTrue(lock.acquired)

    def test_context_manager(self):
        with StoreLock(self.tmp, "reviews") as lk:
            self.assertTrue(lk.acquired)
            self.assertTrue(os.path.exists(_lock_path(self.tmp)))
        self.assertFalse(os.path.exists(_lock_path(self.tmp)))

    def test_release_idempotent(self):
        lock = StoreLock(self.tmp, "x")
        lock.acquire()
        lock.release()
        lock.release()                       # 2e release ne lève pas
        self.assertFalse(lock.acquired)


class TestPidAlive(unittest.TestCase):
    def test_current_pid_alive(self):
        self.assertTrue(_pid_alive(os.getpid()))

    def test_dead_pid(self):
        self.assertFalse(_pid_alive(999999))

    def test_none_or_zero(self):
        self.assertFalse(_pid_alive(None))
        self.assertFalse(_pid_alive(0))


if __name__ == "__main__":
    unittest.main()
