import importlib.util
import json
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "check_review_delivery.py"
SPEC = importlib.util.spec_from_file_location("review_delivery", MODULE_PATH)
review_delivery = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = review_delivery
SPEC.loader.exec_module(review_delivery)


class ReviewDeliveryTests(unittest.TestCase):
    def reviewed(self, target: str = "2026-08-25") -> dict:
        return {
            "schemaVersion": 1,
            "targetDate": target,
            "status": "no_quality_entries",
            "counts": {"published": 0, "features": 0, "editorial": 0},
            "entries": [],
        }

    def test_valid_reviewed_accepts_empty_quality_day(self):
        self.assertTrue(review_delivery.valid_reviewed(self.reviewed(), "2026-08-25"))

    def test_valid_reviewed_rejects_count_mismatch(self):
        payload = self.reviewed()
        payload["counts"]["published"] = 1
        self.assertFalse(review_delivery.valid_reviewed(payload, "2026-08-25"))

    def test_bridge_requires_matching_row_and_parseable_payload(self):
        payload = json.dumps(self.reviewed(), separators=(",", ":"))
        csv_text = (
            "target_date,status,reviewed_json,updated_at,github_write_status,schema_version\n"
            f'2026-08-25,no_quality_entries,"{payload.replace(chr(34), chr(34) * 2)}",2026-08-26T13:20:00+08:00,sheet_bridge_ready,1\n'
        )
        self.assertTrue(review_delivery.bridge_has_target(csv_text, "2026-08-25"))
        self.assertFalse(review_delivery.bridge_has_target(csv_text, "2026-08-24"))


if __name__ == "__main__":
    unittest.main()
