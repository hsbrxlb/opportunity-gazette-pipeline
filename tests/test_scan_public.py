import importlib.util
import sys
import unittest
from pathlib import Path


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "scan_public.py"
SPEC = importlib.util.spec_from_file_location("scan_public", MODULE_PATH)
scan_public = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules[SPEC.name] = scan_public
SPEC.loader.exec_module(scan_public)


class PublicScanTests(unittest.TestCase):
    def test_redacted_assignment_is_allowed(self):
        fixture = '"excerpt": "' + "password" + ': [redacted]"'
        self.assertNotIn("credential-field", scan_public.scan_text(fixture))

    def test_unredacted_assignment_is_rejected(self):
        fixture = '"excerpt": "' + "password" + ': copied-value"'
        self.assertIn("credential-field", scan_public.scan_text(fixture))

    def test_token_shape_is_still_rejected(self):
        self.assertIn("token-shape", scan_public.scan_text("sk-" + "abcdefghijklmnop1234"))

    def test_redacted_local_user_path_is_allowed(self):
        self.assertNotIn("local-user-path", scan_public.scan_text("/" + "Users/[redacted]/project/file"))

    def test_named_local_user_path_is_rejected(self):
        self.assertIn("local-user-path", scan_public.scan_text("/" + "Users/" + "alice/project/file"))


if __name__ == "__main__":
    unittest.main()
