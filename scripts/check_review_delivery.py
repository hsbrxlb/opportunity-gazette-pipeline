#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import datetime as dt
import io
import json
import urllib.error
import urllib.request
from typing import Any
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Shanghai")
RAW_ROOT = "https://raw.githubusercontent.com/hsbrxlb/opportunity-gazette-pipeline/main"


def fetch_text(url: str) -> tuple[int, str]:
    request = urllib.request.Request(url, headers={"User-Agent": "OpportunityGazetteWatchdog/1.0"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            return response.status, response.read(3_000_000).decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, ""


def valid_reviewed(payload: Any, target_date: str) -> bool:
    if not isinstance(payload, dict) or payload.get("schemaVersion") != 1:
        return False
    if payload.get("targetDate") != target_date:
        return False
    if payload.get("status") not in {"ready_for_publish", "no_quality_entries"}:
        return False
    entries = payload.get("entries")
    counts = payload.get("counts")
    if not isinstance(entries, list) or not isinstance(counts, dict):
        return False
    published = counts.get("published")
    return published == len(entries) and counts.get("features", 0) + counts.get("editorial", 0) == published


def bridge_has_target(csv_text: str, target_date: str) -> bool:
    for row in csv.DictReader(io.StringIO(csv_text)):
        if row.get("target_date") != target_date:
            continue
        try:
            payload = json.loads(row.get("reviewed_json") or "")
        except json.JSONDecodeError:
            return False
        return (
            row.get("status") == payload.get("status")
            and row.get("schema_version") == "1"
            and valid_reviewed(payload, target_date)
        )
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date")
    parser.add_argument("--sheet-csv-url", required=True)
    args = parser.parse_args()
    target = args.date or (dt.datetime.now(TIMEZONE).date() - dt.timedelta(days=1)).isoformat()
    dt.date.fromisoformat(target)

    candidate_status, _ = fetch_text(f"{RAW_ROOT}/candidates/{target}.json")
    if candidate_status != 200:
        raise SystemExit(f"candidate_missing target_date={target} http={candidate_status}")

    reviewed_status, reviewed_text = fetch_text(f"{RAW_ROOT}/reviewed/{target}.json")
    if reviewed_status == 200:
        try:
            reviewed = json.loads(reviewed_text)
        except json.JSONDecodeError:
            raise SystemExit(f"reviewed_invalid_json target_date={target}")
        if valid_reviewed(reviewed, target):
            print(f"review_delivery_ok target_date={target} source=github")
            return 0
        raise SystemExit(f"reviewed_invalid_schema target_date={target}")
    if reviewed_status != 404:
        raise SystemExit(f"reviewed_unexpected_http target_date={target} http={reviewed_status}")

    sheet_status, sheet_text = fetch_text(args.sheet_csv_url)
    if sheet_status != 200:
        raise SystemExit(f"sheet_bridge_unavailable target_date={target} http={sheet_status}")
    if bridge_has_target(sheet_text, target):
        print(f"review_delivery_ok target_date={target} source=sheet")
        return 0
    raise SystemExit(f"review_delivery_missing target_date={target} candidate_exists=true")


if __name__ == "__main__":
    raise SystemExit(main())
