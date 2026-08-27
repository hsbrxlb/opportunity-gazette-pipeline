# Opportunity Gazette Pipeline

Public, credential-free collection and reviewed-data handoff for [Opportunity Gazette](https://hsbrxlb.github.io/opportunity-gazette/).

## Daily flow

1. GitHub Actions runs at 12:23 Asia/Shanghai and writes the full public archive to `candidates/YYYY-MM-DD.json` plus a source-diverse, maximum-48-item `review_queue/YYYY-MM-DD.json`.
2. A normal ChatGPT scheduled task reads only the review queue, verifies the strongest sources, and writes its decisions to the private editorial Sheet.
3. The task writes publication-safe reviewed JSON to the Sheet's dedicated public bridge row; it does not depend on GitHub Contents write permission.
4. The website repository validates and merges the Sheet-reviewed entries before deploying GitHub Pages.
5. A 15:30 Asia/Shanghai watchdog fails visibly if candidates exist but neither reviewed GitHub data nor a valid Sheet bridge row was delivered.

The collector uses public APIs and pages only. It does not use browser sessions, local files, private messages, passwords, cookies, or long-lived credentials. Login-gated sources remain explicit failures for later human review.

## Local checks

```bash
python3 -m unittest discover -s tests -v
python3 src/collect.py --date 2026-08-16
python3 scripts/validate.py
python3 scripts/scan_public.py
python3 scripts/check_review_delivery.py --date 2026-08-16 --sheet-csv-url '<public-safe bridge CSV URL>'
```

The standard GitHub Actions `GITHUB_TOKEN` is ephemeral and is used only by the workflow runtime to read public GitHub data and persist generated candidate files in this repository.
