#!/usr/bin/env python3
from __future__ import annotations

import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
patterns = {
    "local-user-path": re.compile(r"/" + r"Users/[^/]+/"),
    "credential-field": re.compile(r"(?i)\b(cookie|set-cookie|authorization|bearer|password|passwd|secret|session credential)\b\s*[:=]"),
    "token-shape": re.compile(r"\b(?:gh[opsu]_|sk-)[A-Za-z0-9_-]{16,}\b"),
}
skip = {".git"}
findings: list[str] = []
for path in ROOT.rglob("*"):
    if not path.is_file() or any(part in skip for part in path.parts):
        continue
    if path.suffix.lower() not in {".py", ".json", ".jsonl", ".md", ".yml", ".yaml", ".txt"}:
        continue
    text = path.read_text(encoding="utf-8", errors="ignore")
    for label, pattern in patterns.items():
        if pattern.search(text):
            findings.append(f"{label}: {path.relative_to(ROOT)}")
if findings:
    raise SystemExit("\n".join(findings))
print("Public repository scan passed.")
