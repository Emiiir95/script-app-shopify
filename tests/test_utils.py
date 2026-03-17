"""
Tests unitaires — utils/

Couvre :
  - utils/cost_tracker.py : CostTracker
  - utils/checkpoint.py   : save_progress, load_progress, clear_progress
  - utils/logger.py       : log (also_print, levels)
"""
import json
import os
import tempfile
import unittest
from io import StringIO
from unittest.mock import MagicMock, patch

from utils.checkpoint import (
    clear_progress, load_progress, save_progress,
    save_generated_reviews, load_generated_reviews, clear_generated_reviews,
)
from utils.cost_tracker import PRICE_INPUT_PER_M, PRICE_OUTPUT_PER_M, CostTracker


# ── CostTracker ───────────────────────────────────────────────────────────────

class TestCostTrackerInit(unittest.TestCase):
    def test_starts_at_zero(self):
        tracker = CostTracker()
        self.assertEqual(tracker.calls, 0)
        self.assertEqual(tracker.total_input_tokens, 0)
        self.assertEqual(tracker.total_output_tokens, 0)
        self.assertEqual(tracker.cost_usd, 0.0)


class TestCostTrackerAdd(unittest.TestCase):
    def _usage(self, prompt=0, completion=0):
        u = MagicMock()
        u.prompt_tokens     = prompt
        u.completion_tokens = completion
        return u

    def test_increments_calls(self):
        tracker = CostTracker()
        tracker.add(self._usage(100, 50))
        self.assertEqual(tracker.calls, 1)

    def test_accumulates_tokens(self):
        tracker = CostTracker()
        tracker.add(self._usage(1000, 500))
        tracker.add(self._usage(200,  100))
        self.assertEqual(tracker.total_input_tokens, 1200)
        self.assertEqual(tracker.total_output_tokens, 600)

    def test_multiple_calls_increment_count(self):
        tracker = CostTracker()
        for _ in range(5):
            tracker.add(self._usage(10, 10))
        self.assertEqual(tracker.calls, 5)


class TestCostTrackerCostUsd(unittest.TestCase):
    def test_zero_tokens_zero_cost(self):
        self.assertEqual(CostTracker().cost_usd, 0.0)

    def test_exact_one_million_input_tokens(self):
        tracker = CostTracker()
        u = MagicMock()
        u.prompt_tokens     = 1_000_000
        u.completion_tokens = 0
        tracker.add(u)
        self.assertAlmostEqual(tracker.cost_usd, PRICE_INPUT_PER_M, places=6)

    def test_exact_one_million_output_tokens(self):
        tracker = CostTracker()
        u = MagicMock()
        u.prompt_tokens     = 0
        u.completion_tokens = 1_000_000
        tracker.add(u)
        self.assertAlmostEqual(tracker.cost_usd, PRICE_OUTPUT_PER_M, places=6)

    def test_combined_cost_formula(self):
        tracker = CostTracker()
        u = MagicMock()
        u.prompt_tokens     = 1_000_000
        u.completion_tokens = 1_000_000
        tracker.add(u)
        expected = PRICE_INPUT_PER_M + PRICE_OUTPUT_PER_M
        self.assertAlmostEqual(tracker.cost_usd, expected, places=6)


class TestCostTrackerSummary(unittest.TestCase):
    def test_summary_contains_calls_and_tokens(self):
        tracker = CostTracker()
        u = MagicMock()
        u.prompt_tokens     = 500
        u.completion_tokens = 200
        tracker.add(u)
        summary = tracker.summary()
        self.assertIn("1", summary)    # 1 appel
        self.assertIn("500", summary)
        self.assertIn("200", summary)
        self.assertIn("USD", summary)

    def test_summary_returns_string(self):
        self.assertIsInstance(CostTracker().summary(), str)


# ── Checkpoint ────────────────────────────────────────────────────────────────

class TestSaveProgress(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _progress_path(self):
        return os.path.join(self.tmpdir, "progress.json")

    def test_creates_progress_file(self):
        save_progress(self.tmpdir, 3, ["prod-a"])
        self.assertTrue(os.path.exists(self._progress_path()))

    def test_file_contains_correct_data(self):
        save_progress(self.tmpdir, 7, ["prod-a", "prod-b"])
        with open(self._progress_path()) as f:
            data = json.load(f)
        self.assertEqual(data["last_index"], 7)
        self.assertEqual(data["completed"], ["prod-a", "prod-b"])

    def test_overwrites_previous_progress(self):
        save_progress(self.tmpdir, 1, ["prod-a"])
        save_progress(self.tmpdir, 5, ["prod-a", "prod-b", "prod-c"])
        with open(self._progress_path()) as f:
            data = json.load(f)
        self.assertEqual(data["last_index"], 5)
        self.assertEqual(len(data["completed"]), 3)


class TestLoadProgress(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_returns_saved_values(self):
        save_progress(self.tmpdir, 5, ["prod-a", "prod-b"])
        idx, handles = load_progress(self.tmpdir)
        self.assertEqual(idx, 5)
        self.assertEqual(handles, ["prod-a", "prod-b"])

    def test_returns_default_when_no_file(self):
        idx, handles = load_progress(self.tmpdir)
        self.assertEqual(idx, -1)
        self.assertEqual(handles, [])

    def test_returns_default_on_corrupt_json(self):
        path = os.path.join(self.tmpdir, "progress.json")
        with open(path, "w") as f:
            f.write("not valid json {{{")
        idx, handles = load_progress(self.tmpdir)
        self.assertEqual(idx, -1)
        self.assertEqual(handles, [])

    def test_returns_default_on_empty_file(self):
        path = os.path.join(self.tmpdir, "progress.json")
        open(path, "w").close()
        idx, handles = load_progress(self.tmpdir)
        self.assertEqual(idx, -1)
        self.assertEqual(handles, [])

    def test_returns_default_for_missing_keys(self):
        path = os.path.join(self.tmpdir, "progress.json")
        with open(path, "w") as f:
            json.dump({}, f)
        idx, handles = load_progress(self.tmpdir)
        self.assertEqual(idx, -1)
        self.assertEqual(handles, [])


class TestClearProgress(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_removes_progress_file(self):
        save_progress(self.tmpdir, 0, [])
        clear_progress(self.tmpdir)
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, "progress.json")))

    def test_no_error_when_file_does_not_exist(self):
        # Ne doit pas lever d'exception
        clear_progress(self.tmpdir)

    def test_load_returns_default_after_clear(self):
        save_progress(self.tmpdir, 3, ["prod-a"])
        clear_progress(self.tmpdir)
        idx, handles = load_progress(self.tmpdir)
        self.assertEqual(idx, -1)
        self.assertEqual(handles, [])


# ── Logger ────────────────────────────────────────────────────────────────────

class TestLogger(unittest.TestCase):
    @patch("sys.stdout", new_callable=StringIO)
    def test_also_print_true_prints_to_stdout(self, mock_stdout):
        from utils.logger import log
        log("test message info", also_print=True)
        output = mock_stdout.getvalue()
        self.assertIn("test message info", output)

    @patch("sys.stdout", new_callable=StringIO)
    def test_also_print_false_does_not_print(self, mock_stdout):
        from utils.logger import log
        log("silent message", also_print=False)
        self.assertEqual(mock_stdout.getvalue(), "")

    @patch("sys.stdout", new_callable=StringIO)
    def test_warning_prefix_in_output(self, mock_stdout):
        from utils.logger import log
        log("attention ici", level="warning", also_print=True)
        self.assertIn("[WARN]", mock_stdout.getvalue())

    @patch("sys.stdout", new_callable=StringIO)
    def test_error_prefix_in_output(self, mock_stdout):
        from utils.logger import log
        log("une erreur", level="error", also_print=True)
        self.assertIn("[ERREUR]", mock_stdout.getvalue())

    @patch("sys.stdout", new_callable=StringIO)
    def test_info_prefix_in_output(self, mock_stdout):
        from utils.logger import log
        log("une info", level="info", also_print=True)
        self.assertIn("[INFO]", mock_stdout.getvalue())


# ── Generated reviews cache ───────────────────────────────────────────────────

class TestSaveGeneratedReviews(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def _cache_path(self):
        return os.path.join(self.tmpdir, "reviews_generated.json")

    def test_creates_file(self):
        save_generated_reviews(self.tmpdir, [{"handle": "prod-a"}])
        self.assertTrue(os.path.exists(self._cache_path()))

    def test_stores_products_data(self):
        data = [{"handle": "prod-a", "reviews": []}]
        save_generated_reviews(self.tmpdir, data)
        with open(self._cache_path(), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["products_data"], data)

    def test_stores_generated_at_timestamp(self):
        save_generated_reviews(self.tmpdir, [])
        with open(self._cache_path(), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertIn("generated_at", saved)

    def test_stores_store_url(self):
        save_generated_reviews(self.tmpdir, [], store_url="mystore.myshopify.com")
        with open(self._cache_path(), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["store_url"], "mystore.myshopify.com")

    def test_overwrites_previous_cache(self):
        save_generated_reviews(self.tmpdir, [{"handle": "old"}])
        save_generated_reviews(self.tmpdir, [{"handle": "new"}])
        with open(self._cache_path(), encoding="utf-8") as f:
            saved = json.load(f)
        self.assertEqual(saved["products_data"][0]["handle"], "new")


class TestLoadGeneratedReviews(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_returns_none_when_no_file(self):
        self.assertIsNone(load_generated_reviews(self.tmpdir))

    def test_returns_saved_data(self):
        data = [{"handle": "prod-a"}]
        save_generated_reviews(self.tmpdir, data)
        result = load_generated_reviews(self.tmpdir)
        self.assertEqual(result["products_data"], data)

    def test_returns_none_on_corrupt_file(self):
        path = os.path.join(self.tmpdir, "reviews_generated.json")
        with open(path, "w") as f:
            f.write("not valid json {{{")
        self.assertIsNone(load_generated_reviews(self.tmpdir))

    def test_returns_none_on_empty_file(self):
        path = os.path.join(self.tmpdir, "reviews_generated.json")
        open(path, "w").close()
        self.assertIsNone(load_generated_reviews(self.tmpdir))


class TestClearGeneratedReviews(unittest.TestCase):
    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()

    def test_removes_file(self):
        save_generated_reviews(self.tmpdir, [])
        clear_generated_reviews(self.tmpdir)
        self.assertFalse(os.path.exists(os.path.join(self.tmpdir, "reviews_generated.json")))

    def test_no_error_when_file_does_not_exist(self):
        clear_generated_reviews(self.tmpdir)  # ne doit pas lever d'exception

    def test_load_returns_none_after_clear(self):
        save_generated_reviews(self.tmpdir, [{"handle": "prod"}])
        clear_generated_reviews(self.tmpdir)
        self.assertIsNone(load_generated_reviews(self.tmpdir))


if __name__ == "__main__":
    unittest.main()
