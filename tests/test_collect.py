import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "collect.py"
SPEC = importlib.util.spec_from_file_location("collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


class CollectorTests(unittest.TestCase):
    def test_url_normalization_removes_tracking(self):
        self.assertEqual(
            collector.canonical_url("https://Example.com/path/?utm_source=x&keep=1#part"),
            "https://example.com/path?keep=1",
        )

    def test_exact_url_and_title_duplicates_are_rejected(self):
        run = collector.Collector("2026-08-16")
        first = run.add(source="x", source_type="public", title="AI automation tool for teams", url="https://example.com/a", published_at="2026-08-16")
        duplicate = run.add(source="y", source_type="public", title="AI automation tool for teams", url="https://example.com/a?utm_source=test", published_at="2026-08-16")
        self.assertTrue(first)
        self.assertFalse(duplicate)
        self.assertEqual(len(run.candidates), 1)

    def test_payload_is_bounded_and_reconciled(self):
        run = collector.Collector("2026-08-16")
        run.add(source="x", source_type="public", title="GitHub automation failure report", url="https://example.com/one", published_at="2026-08-16")
        run.add_source("x", "ok", 1, "ok")
        payload = run.payload()
        self.assertEqual(payload["counts"]["candidates"], 1)
        self.assertEqual(payload["targetDate"], "2026-08-16")
        self.assertEqual(payload["status"], "ready_for_review")
        json.dumps(payload)


if __name__ == "__main__":
    unittest.main()
