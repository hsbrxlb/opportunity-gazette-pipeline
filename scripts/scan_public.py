#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
patterns = {
    "local-user-path": re.compile(r"/" + r"Users/[^/]+/"),
    "credential-field": re.compile(
        r"(?i)\b(cookie|set-cookie|authorization|bearer|password|passwd|secret|session credential)"
        r"\b\s*[:=]\s*(?!\[redacted\]|<redacted>|redacted\b)[^\s,}\]]+"
    ),
    "token-shape": re.compile(r"\b(?:gh[opsu]_|sk-)[A-Za-z0-9_-]{16,}\b"),
}
skip = {".git"}


def scan_text(text: str) -> list[str]:
    return [label for label, pattern in patterns.items() if pattern.search(text)]


def scan_root(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or any(part in skip for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".json", ".jsonl", ".md", ".yml", ".yaml", ".txt"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for label in scan_text(text):
            findings.append(f"{label}: {path.relative_to(root)}")
    return findings


def main() -> int:
    findings = scan_root()
    if findings:
        raise SystemExit("\n".join(findings))
    print("Public repository scan passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
