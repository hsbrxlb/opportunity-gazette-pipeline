# Opportunity Gazette Pipeline

Public, credential-free collection and reviewed-data handoff for [Opportunity Gazette](https://hsbrxlb.github.io/opportunity-gazette/).

## Daily flow

1. GitHub Actions runs at 12:23 Asia/Shanghai and writes `candidates/YYYY-MM-DD.json`.
2. A normal ChatGPT scheduled task reads that bounded candidate file, verifies the strongest sources, and writes its decisions to the private editorial Sheet.
3. The task writes only publication-safe output to `reviewed/YYYY-MM-DD.json`.
4. The website repository validates and merges reviewed entries before deploying GitHub Pages.

The collector uses public APIs and pages only. It does not use browser sessions, local files, private messages, passwords, cookies, or long-lived credentials. Login-gated sources remain explicit failures or manual supplements.

## Local checks

```bash
python3 -m unittest discover -s tests -v
python3 src/collect.py --date 2026-08-16
python3 scripts/validate.py
python3 scripts/scan_public.py
```

The standard GitHub Actions `GITHUB_TOKEN` is ephemeral and is used only by the workflow runtime to read public GitHub data and persist generated candidate files in this repository.
