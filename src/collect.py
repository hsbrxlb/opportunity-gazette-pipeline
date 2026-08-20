#!/usr/bin/env python3
"""Collect public opportunity signals into a bounded, review-ready candidate file."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo


TIMEZONE = ZoneInfo("Asia/Shanghai")
ROOT = Path(__file__).resolve().parents[1]
USER_AGENT = "OpportunityGazettePipeline/1.0 (+https://github.com/hsbrxlb/opportunity-gazette-pipeline)"
MAX_CANDIDATES = 150
RELEVANCE = {
    "ai", "agent", "automation", "workflow", "developer", "tool", "saas",
    "productivity", "plugin", "browser", "local", "privacy", "monitoring",
    "github", "startup", "founder", "customer", "billing", "cost", "failure",
    "人工智能", "自动化", "工具", "开发", "创业", "增长", "工作流", "失败",
}
CREDENTIAL_ASSIGNMENT = re.compile(
    r"(?i)\b(cookie|set-cookie|authorization|bearer|password|passwd|secret|session credential)"
    r"\b(\s*[:=]\s*)([^\r\n,;]{1,200})"
)


def redact_sensitive_assignments(value: Any) -> str:
    """Remove copied credential-like assignments from public source text."""
    text = str(value or "")
    return CREDENTIAL_ASSIGNMENT.sub(lambda match: f"{match.group(1)}{match.group(2)}[redacted]", text)


def clean(value: Any, limit: int = 700) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit]


def canonical_url(value: str) -> str:
    parsed = urllib.parse.urlsplit(value)
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=False)
    safe_query = [(key, val) for key, val in query if not key.lower().startswith("utm_") and key.lower() not in {"ref", "source", "campaign"}]
    return urllib.parse.urlunsplit((parsed.scheme.lower(), parsed.netloc.lower(), parsed.path.rstrip("/"), urllib.parse.urlencode(safe_query), ""))


def stable_id(prefix: str, *parts: str) -> str:
    raw = "|".join(clean(part).casefold() for part in parts)
    return f"{prefix}-{hashlib.sha256(raw.encode('utf-8')).hexdigest()[:12]}"


def request_bytes(url: str, headers: dict[str, str] | None = None, timeout: int = 25) -> bytes:
    merged = {"User-Agent": USER_AGENT, "Accept": "application/json, application/rss+xml, text/xml;q=0.9, */*;q=0.5"}
    if headers:
        merged.update(headers)
    request = urllib.request.Request(url, headers=merged)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read(3_000_000)


def request_json(url: str, headers: dict[str, str] | None = None) -> Any:
    return json.loads(request_bytes(url, headers=headers).decode("utf-8", errors="replace"))


@dataclass
class Collector:
    target_date: str
    candidates: list[dict[str, Any]] = field(default_factory=list)
    sources: list[dict[str, Any]] = field(default_factory=list)
    raw_count: int = 0
    _seen_urls: set[str] = field(default_factory=set)
    _seen_titles: set[str] = field(default_factory=set)

    @property
    def day_start(self) -> dt.datetime:
        return dt.datetime.fromisoformat(self.target_date).replace(tzinfo=TIMEZONE)

    @property
    def day_end(self) -> dt.datetime:
        return self.day_start + dt.timedelta(days=1)

    def add_source(self, name: str, status: str, count: int, detail: str, source_type: str = "public") -> None:
        self.sources.append({"source": name, "status": status, "count": count, "detail": clean(detail, 300), "sourceType": source_type})

    def run_source(self, name: str, fn: Callable[[], int], source_type: str = "public") -> None:
        before = len(self.candidates)
        try:
            observed = fn()
            added = len(self.candidates) - before
            self.add_source(name, "ok" if observed else "empty", added, f"observed={observed}; added_after_dedupe={added}", source_type)
        except urllib.error.HTTPError as exc:
            status = "rate_limited_or_blocked" if exc.code in {401, 403, 429} else "failed"
            self.add_source(name, status, 0, f"HTTP {exc.code}", source_type)
        except Exception as exc:  # one source must never stop the daily collector
            self.add_source(name, "failed", 0, f"{type(exc).__name__}: {clean(exc, 180)}", source_type)

    def add(self, *, source: str, source_type: str, title: str, url: str, published_at: str,
            excerpt: str = "", metrics: dict[str, Any] | None = None, topics: list[str] | None = None,
            boundary: str = "Public source signal; requires editorial verification before publication.") -> bool:
        self.raw_count += 1
        title = clean(redact_sensitive_assignments(title), 240)
        excerpt = redact_sensitive_assignments(excerpt)
        url = canonical_url(clean(url, 900))
        if len(title) < 8 or not url.startswith(("https://", "http://")):
            return False
        title_key = re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", title.casefold())
        if url in self._seen_urls or title_key in self._seen_titles:
            return False
        text = f"{title} {excerpt}".casefold()
        if not any(term in text for term in RELEVANCE):
            return False
        self._seen_urls.add(url)
        self._seen_titles.add(title_key)
        self.candidates.append({
            "id": stable_id("candidate", self.target_date, url, title),
            "targetDate": self.target_date,
            "source": source,
            "sourceType": source_type,
            "title": title,
            "url": url,
            "publishedAt": clean(published_at, 80),
            "excerpt": clean(excerpt, 650),
            "metrics": metrics or {},
            "topics": topics or [],
            "accessStatus": "public",
            "boundary": boundary,
        })
        return True

    def collect_hacker_news(self) -> int:
        start = int(self.day_start.astimezone(dt.timezone.utc).timestamp())
        end = int(self.day_end.astimezone(dt.timezone.utc).timestamp())
        observed = 0
        for page in range(3):
            params = urllib.parse.urlencode({
                "tags": "story",
                "numericFilters": f"created_at_i>={start},created_at_i<{end}",
                "hitsPerPage": 100,
                "page": page,
            })
            data = request_json(f"https://hn.algolia.com/api/v1/search_by_date?{params}")
            hits = data.get("hits", [])
            observed += len(hits)
            for item in hits:
                object_id = str(item.get("objectID", ""))
                self.add(
                    source="Hacker News",
                    source_type="community_discussion",
                    title=item.get("title") or item.get("story_title") or "",
                    url=item.get("url") or f"https://news.ycombinator.com/item?id={object_id}",
                    published_at=item.get("created_at", ""),
                    excerpt=item.get("story_text") or item.get("comment_text") or "",
                    metrics={"points": item.get("points") or 0, "comments": item.get("num_comments") or 0},
                    topics=["public-web", "developer-tools"],
                )
            if len(hits) < 100:
                break
        return observed

    def collect_github(self) -> int:
        token = os.environ.get("GITHUB_TOKEN", "")
        headers = {"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
        if token:
            headers["Authorization"] = f"Bearer {token}"
        queries = [
            f'created:{self.target_date} is:issue (AI OR agent OR automation) in:title,body',
            f'created:{self.target_date} is:issue (workflow OR billing OR monitoring OR failure) in:title,body',
            f'created:{self.target_date} is:issue (tool OR plugin OR browser OR privacy) in:title,body',
        ]
        observed = 0
        for query in queries:
            params = urllib.parse.urlencode({"q": query, "sort": "comments", "order": "desc", "per_page": 100})
            data = request_json(f"https://api.github.com/search/issues?{params}", headers=headers)
            items = data.get("items", [])
            observed += len(items)
            for item in items:
                repo_url = str(item.get("repository_url", ""))
                repo_name = repo_url.split("/repos/")[-1] if "/repos/" in repo_url else "GitHub"
                self.add(
                    source=f"GitHub Issue — {repo_name}",
                    source_type="production_or_user_issue",
                    title=item.get("title", ""),
                    url=item.get("html_url", ""),
                    published_at=item.get("created_at", ""),
                    excerpt=item.get("body") or "",
                    metrics={"comments": item.get("comments") or 0, "score": item.get("score") or 0},
                    topics=["github", "automation"],
                    boundary="Public issue report. It can support a concrete case, not market-wide demand without corroboration.",
                )
        return observed

    def collect_devto(self) -> int:
        observed = 0
        for tag in ("ai", "programming", "productivity", "webdev"):
            params = urllib.parse.urlencode({"tag": tag, "per_page": 100, "page": 1})
            items = request_json(f"https://dev.to/api/articles?{params}")
            observed += len(items)
            for item in items:
                published = str(item.get("published_at", ""))
                if not published.startswith(self.target_date):
                    continue
                self.add(
                    source=f"DEV.to #{tag}",
                    source_type="technical_article",
                    title=item.get("title", ""),
                    url=item.get("url", ""),
                    published_at=published,
                    excerpt=item.get("description") or "",
                    metrics={"comments": item.get("comments_count") or 0, "reactions": item.get("public_reactions_count") or 0},
                    topics=[tag, "technical-case"],
                    boundary="Public article signal. Author claims and tutorials require result-level verification.",
                )
        return observed

    def collect_v2ex(self) -> int:
        items = request_json("https://www.v2ex.com/api/topics/latest.json")
        for item in items:
            created = dt.datetime.fromtimestamp(int(item.get("created", 0)), tz=dt.timezone.utc).astimezone(TIMEZONE)
            if created.date().isoformat() != self.target_date:
                continue
            self.add(
                source="V2EX",
                source_type="chinese_developer_forum",
                title=item.get("title", ""),
                url=item.get("url", ""),
                published_at=created.isoformat(),
                excerpt=item.get("content") or "",
                metrics={"replies": item.get("replies") or 0},
                topics=["chinese-developers"],
            )
        return len(items)

    def collect_stack_exchange(self) -> int:
        start = int(self.day_start.astimezone(dt.timezone.utc).timestamp())
        end = int(self.day_end.astimezone(dt.timezone.utc).timestamp())
        observed = 0
        for tagged in ("artificial-intelligence", "automation", "github-actions"):
            params = urllib.parse.urlencode({
                "site": "stackoverflow", "fromdate": start, "todate": end,
                "order": "desc", "sort": "activity", "pagesize": 100, "tagged": tagged,
            })
            data = request_json(f"https://api.stackexchange.com/2.3/questions?{params}")
            items = data.get("items", [])
            observed += len(items)
            for item in items:
                created = dt.datetime.fromtimestamp(int(item.get("creation_date", 0)), tz=dt.timezone.utc).isoformat()
                self.add(
                    source=f"Stack Overflow #{tagged}",
                    source_type="developer_question",
                    title=item.get("title", ""),
                    url=item.get("link", ""),
                    published_at=created,
                    excerpt=" ".join(item.get("tags", [])),
                    metrics={"score": item.get("score") or 0, "answers": item.get("answer_count") or 0, "views": item.get("view_count") or 0},
                    topics=[tagged, "developer-pain"],
                )
        return observed

    def collect_app_store(self) -> int:
        observed = 0
        for country, term in (("us", "AI notes"), ("us", "AI coding"), ("us", "automation productivity"), ("cn", "AI 语音笔记"), ("cn", "AI 效率工具")):
            params = urllib.parse.urlencode({"term": term, "country": country, "entity": "software", "limit": 100})
            data = request_json(f"https://itunes.apple.com/search?{params}")
            items = data.get("results", [])
            observed += len(items)
            for item in items:
                release = str(item.get("currentVersionReleaseDate") or item.get("releaseDate") or "")
                if not release.startswith(self.target_date):
                    continue
                self.add(
                    source=f"App Store Search {country.upper()}",
                    source_type="app_market",
                    title=item.get("trackName", ""),
                    url=item.get("trackViewUrl", ""),
                    published_at=release,
                    excerpt=item.get("description") or "",
                    metrics={"ratings": item.get("userRatingCount") or 0, "rating": item.get("averageUserRating") or 0},
                    topics=["app-store", "product-signal"],
                    boundary="App metadata and ratings support product existence and reception, not paid conversion or retention.",
                )
        return observed

    def collect_reddit(self) -> int:
        observed = 0
        for subreddit in ("SideProject", "SaaS", "somebodymakethis", "indiehackers"):
            data = request_json(f"https://www.reddit.com/r/{subreddit}/new.json?limit=100&raw_json=1")
            children = data.get("data", {}).get("children", [])
            observed += len(children)
            for child in children:
                item = child.get("data", {})
                created = dt.datetime.fromtimestamp(float(item.get("created_utc", 0)), tz=dt.timezone.utc).astimezone(TIMEZONE)
                if created.date().isoformat() != self.target_date:
                    continue
                self.add(
                    source=f"Reddit r/{subreddit}",
                    source_type="community_post",
                    title=item.get("title", ""),
                    url="https://www.reddit.com" + str(item.get("permalink", "")),
                    published_at=created.isoformat(),
                    excerpt=item.get("selftext") or "",
                    metrics={"score": item.get("score") or 0, "comments": item.get("num_comments") or 0},
                    topics=["community", "startup"],
                )
        return observed

    def score(self, candidate: dict[str, Any]) -> tuple[float, str]:
        metrics = candidate.get("metrics", {})
        text = f"{candidate.get('title', '')} {candidate.get('excerpt', '')}".casefold()
        pain_markers = (
            "bug", "fail", "broken", "error", "duplicate", "waste", "cost", "billing",
            "privacy", "security", "over budget", "cannot", "can't", "need help", "problem",
            "故障", "失败", "重复", "浪费", "成本", "隐私", "安全", "求助", "问题",
        )
        value = 12.0 * sum(marker in text for marker in pain_markers)
        for key in ("comments", "replies", "answers", "points", "score", "ratings", "views"):
            try:
                metric = max(0.0, float(metrics.get(key, 0) or 0))
            except (TypeError, ValueError):
                metric = 0.0
            value += math.log1p(metric)
        if any(marker in text for marker in ("[control]", "worker registry", "coordination ledger", "hourly controller")):
            value -= 18
        return value, candidate.get("publishedAt", "")

    def payload(self) -> dict[str, Any]:
        ranked = sorted(self.candidates, key=self.score, reverse=True)
        caps = {"GitHub": 65, "Hacker News": 45, "DEV.to": 25, "App Store": 15, "other": 20}
        counts: dict[str, int] = {key: 0 for key in caps}
        candidates: list[dict[str, Any]] = []
        for item in ranked:
            source = item.get("source", "")
            group = next((name for name in ("GitHub", "Hacker News", "DEV.to", "App Store") if source.startswith(name)), "other")
            if counts[group] >= caps[group]:
                continue
            counts[group] += 1
            candidates.append(item)
            if len(candidates) >= MAX_CANDIDATES:
                break
        generated = dt.datetime.now(TIMEZONE).isoformat()
        return {
            "schemaVersion": 1,
            "targetDate": self.target_date,
            "generatedAt": generated,
            "status": "ready_for_review",
            "counts": {
                "observed": self.raw_count,
                "candidates": len(candidates),
                "mechanicallyRejectedOrDeduplicated": max(0, self.raw_count - len(candidates)),
                "sourceFailures": sum(source["status"] not in {"ok", "empty"} for source in self.sources),
            },
            "sources": self.sources,
            "candidates": candidates,
            "reviewInstructions": {
                "publishAllPassing": True,
                "allowedKinds": ["opportunity", "case"],
                "allowedQuality": ["feature", "editorial"],
                "requiredFields": ["plain", "audience", "pain", "why", "validation", "risk", "evidence"],
            },
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--date", help="Target date in Asia/Shanghai, default previous complete day")
    parser.add_argument("--output", help="Output path, default candidates/YYYY-MM-DD.json")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = args.date or (dt.datetime.now(TIMEZONE).date() - dt.timedelta(days=1)).isoformat()
    dt.date.fromisoformat(target)
    collector = Collector(target)
    collector.run_source("Hacker News", collector.collect_hacker_news)
    collector.run_source("GitHub Issues", collector.collect_github)
    collector.run_source("DEV.to", collector.collect_devto)
    collector.run_source("V2EX", collector.collect_v2ex)
    collector.run_source("Stack Exchange", collector.collect_stack_exchange)
    collector.run_source("App Store Search", collector.collect_app_store, "runtime_visible_public_api")
    collector.run_source("Reddit", collector.collect_reddit)
    collector.add_source("Product Hunt", "not_configured", 0, "Official API credential is not configured; skipped.", "credential_required")
    collector.add_source("X public search", "needs_manual_supplement", 0, "No stable credential-free date-bounded endpoint.", "manual")
    collector.add_source("微博", "needs_manual_supplement", 0, "Remote collector does not use browser sessions or cookies.", "manual")
    collector.add_source("小红书", "needs_manual_supplement", 0, "Remote collector does not use browser sessions or cookies.", "manual")
    output = Path(args.output) if args.output else ROOT / "candidates" / f"{target}.json"
    payload = collector.payload()
    if output.exists():
        try:
            existing = json.loads(output.read_text(encoding="utf-8"))
            previous = {key: value for key, value in existing.items() if key != "generatedAt"}
            current = {key: value for key, value in payload.items() if key != "generatedAt"}
            if previous == current and existing.get("generatedAt"):
                payload["generatedAt"] = existing["generatedAt"]
        except (OSError, json.JSONDecodeError):
            pass
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    latest = ROOT / "status" / "latest.json"
    latest.parent.mkdir(parents=True, exist_ok=True)
    latest.write_text(json.dumps({
        "schemaVersion": 1,
        "targetDate": target,
        "generatedAt": payload["generatedAt"],
        "status": payload["status"],
        "counts": payload["counts"],
        "candidatePath": f"candidates/{target}.json",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output.relative_to(ROOT)), **payload["counts"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
