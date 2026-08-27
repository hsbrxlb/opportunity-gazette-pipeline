#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
required_candidate = {"id", "targetDate", "source", "sourceType", "title", "url", "publishedAt", "excerpt", "metrics", "topics", "accessStatus", "boundary"}

files = sorted((ROOT / "candidates").glob("*.json"))
if not files:
    raise SystemExit("No candidate files found")
for path in files:
    data = json.loads(path.read_text(encoding="utf-8"))
    if path.stem != data.get("targetDate"):
        raise SystemExit(f"{path.name}: target date mismatch")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or data.get("counts", {}).get("candidates") != len(candidates):
        raise SystemExit(f"{path.name}: candidate count mismatch")
    seen: set[str] = set()
    for item in candidates:
        missing = required_candidate - item.keys()
        if missing:
            raise SystemExit(f"{path.name}: missing {sorted(missing)}")
        if item["id"] in seen:
            raise SystemExit(f"{path.name}: duplicate id {item['id']}")
        seen.add(item["id"])
        if not item["url"].startswith(("http://", "https://")):
            raise SystemExit(f"{path.name}: invalid URL")
print(f"Validated {len(files)} candidate file(s).")

queue_files = sorted((ROOT / "review_queue").glob("*.json"))
for path in queue_files:
    data = json.loads(path.read_text(encoding="utf-8"))
    if path.stem != data.get("targetDate"):
        raise SystemExit(f"{path.name}: review queue target date mismatch")
    candidates = data.get("candidates")
    counts = data.get("counts", {})
    if not isinstance(candidates, list) or counts.get("queuedCandidates") != len(candidates):
        raise SystemExit(f"{path.name}: review queue count mismatch")
    if len(candidates) > 48 or counts.get("fullCandidates", 0) < len(candidates):
        raise SystemExit(f"{path.name}: review queue bounds mismatch")
    if len({item.get("id") for item in candidates}) != len(candidates):
        raise SystemExit(f"{path.name}: duplicate review queue id")
print(f"Validated {len(queue_files)} review queue file(s).")
