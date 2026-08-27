import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "src" / "collect.py"
SPEC = importlib.util.spec_from_file_location("collector", MODULE_PATH)
collector = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = collector
SPEC.loader.exec_module(collector)


class CollectorTests(unittest.TestCase):
    def test_credential_assignments_are_redacted_from_public_text(self):
        run = collector.Collector("2026-08-16")
        run.add(
            source="x",
            source_type="public",
            title="AI automation failure with " + "password" + ": demo-value",
            url="https://example.com/credential-case",
            published_at="2026-08-16",
            excerpt="Authorization" + ": Bearer copied-example; ordinary explanation remains.",
        )
        candidate = run.candidates[0]
        self.assertIn("password: [redacted]", candidate["title"])
        self.assertIn("Authorization: [redacted]", candidate["excerpt"])
        self.assertNotIn("demo-value", candidate["title"])
        self.assertNotIn("copied-example", candidate["excerpt"])

    def test_local_user_paths_are_redacted_from_public_text(self):
        run = collector.Collector("2026-08-16")
        run.add(
            source="x",
            source_type="public",
            title="AI automation failure on a local developer machine",
            url="https://example.com/local-path-case",
            published_at="2026-08-16",
            excerpt="The tool failed under /" + "Users/" + "alice/project/config.json",
        )
        excerpt = run.candidates[0]["excerpt"]
        self.assertIn("/" + "Users/[redacted]/project/config.json", excerpt)
        self.assertNotIn("/" + "Users/" + "alice/", excerpt)

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

    def test_review_queue_is_bounded_diverse_and_keeps_full_count(self):
        run = collector.Collector("2026-08-16")
        groups = [
            ("GitHub Issue — example/repo", 30),
            ("Hacker News", 20),
            ("DEV.to #ai", 12),
            ("App Store Search US", 8),
            ("Stack Overflow #automation", 3),
        ]
        index = 0
        for source, count in groups:
            for _ in range(count):
                index += 1
                run.add(
                    source=source,
                    source_type="public",
                    title=f"AI automation failure report number {index}",
                    url=f"https://example.com/{index}",
                    published_at="2026-08-16",
                    metrics={"comments": count},
                )
        payload = run.payload()
        queue = collector.build_review_queue(payload)
        self.assertEqual(queue["counts"]["fullCandidates"], len(payload["candidates"]))
        self.assertEqual(queue["counts"]["queuedCandidates"], 48)
        self.assertEqual(len(queue["candidates"]), 48)
        selected_sources = {collector.source_group(item["source"]) for item in queue["candidates"]}
        self.assertEqual(selected_sources, {"GitHub", "Hacker News", "DEV.to", "App Store", "other"})

    def test_same_payload_can_preserve_generation_time(self):
        run = collector.Collector("2026-08-16")
        run.add(source="x", source_type="public", title="AI automation failure report", url="https://example.com/one", published_at="2026-08-16")
        first = run.payload()
        second = run.payload()
        previous = {key: value for key, value in first.items() if key != "generatedAt"}
        current = {key: value for key, value in second.items() if key != "generatedAt"}
        self.assertEqual(previous, current)

    def test_negative_or_invalid_metrics_do_not_break_ranking(self):
        run = collector.Collector("2026-08-16")
        candidate = {
            "title": "AI automation failure report",
            "excerpt": "billing problem",
            "publishedAt": "2026-08-16T00:00:00Z",
            "metrics": {"score": -3, "comments": "unknown"},
        }
        score, _ = run.score(candidate)
        self.assertGreaterEqual(score, 0)


if __name__ == "__main__":
    unittest.main()
