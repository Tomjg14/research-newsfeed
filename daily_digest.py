#!/usr/bin/env python3
"""
Daily digest generator + Resend sender.

Env vars (set in GitHub Actions 'env:' with repo Secrets):
  RESEND_API_KEY   required
  TO_EMAIL         required (recipient)
  RESEND_FROM      optional (default: 'AI Digest <onboarding@resend.dev>')
  REPLY_TO         optional (e.g., yourname@hotmail.nl)
  MAX_PER_SOURCE   optional (default 10) — items per source
"""

from __future__ import annotations
import os
import sys
import datetime as dt
from typing import Dict, List, Any

import requests
import yaml

# --- Import your existing fetchers (from your repo) ---
from sources import arxiv as src_arxiv
from sources import openreview as src_openreview
from sources import acl as src_acl
from sources import reddit as src_reddit


# ---------------------------
# Fetch + render
# ---------------------------
def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_all(cfg: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    gf = {
        "lookback_days": int(cfg.get("lookback_days", 7)),
        "include_keywords": cfg.get("include_keywords", []),
        "exclude_keywords": cfg.get("exclude_keywords", []),
        "priority_authors": [a.lower() for a in cfg.get("priority_authors", [])],
    }
    scfg = cfg.get("sources", {}) or {}

    buckets: Dict[str, List[Dict[str, Any]]] = {}

    if (scfg.get("arxiv") or {}).get("enabled", True):
        buckets["arXiv"] = src_arxiv.fetch(scfg.get("arxiv", {}), gf)
    if (scfg.get("openreview") or {}).get("enabled", True):
        buckets["OpenReview"] = src_openreview.fetch(scfg.get("openreview", {}), gf)
    if (scfg.get("acl") or {}).get("enabled", True):
        buckets["ACL Anthology"] = src_acl.fetch(scfg.get("acl", {}), gf)
    if (scfg.get("reddit") or {}).get("enabled", True):
        buckets["Reddit"] = src_reddit.fetch(scfg.get("reddit", {}), gf)

    # sort newest first within each bucket
    for items in buckets.values():
        items.sort(key=lambda x: x.get("published") or dt.datetime.min, reverse=True)

    return buckets


def render_html(buckets: Dict[str, List[Dict[str, Any]]], max_per_source: int = 10) -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    parts: List[str] = [f"<h2>AI &amp; AI Security — Daily Digest ({today})</h2>"]
    for name, items in buckets.items():
        if not items:
            continue
        n = min(len(items), max_per_source)
        parts.append(f"<h3>{name} ({n})</h3>")
        parts.append("<ul>")
        for it in items[:max_per_source]:
            title = (it.get("title") or "").strip()
            link = it.get("pdf") or it.get("link") or "#"
            summary = (it.get("summary") or "").strip()
            if len(summary) > 280:
                summary = summary[:280].rsplit(" ", 1)[0] + "…"
            safe_title = (
                title.replace("&", "&amp;")
                     .replace("<", "&lt;")
                     .replace(">", "&gt;")
            )
            parts.append(
                f"<li><a href=\"{link}\">{safe_title}</a>"
                + (f"<br><small>{summary}</small>" if summary else "")
                + "</li>"
            )
        parts.append("</ul>")
    return "\n".join(parts)


def render_plaintext(buckets: Dict[str, List[Dict[str, Any]]], max_per_source: int = 10) -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    lines: List[str] = [f"AI & AI Security — Daily Digest ({today})", ""]
    for name, items in buckets.items():
        if not items:
            continue
        lines.append(f"{name} (showing up to {max_per_source})")
        for it in items[:max_per_source]:
            title = (it.get("title") or "").strip()
            link = it.get("pdf") or it.get("link") or ""
            summary = (it.get("summary") or "").strip()
            if len(summary) > 280:
                summary = summary[:280].rsplit(" ", 1)[0] + "…"
            lines.append(f"- {title}")
            if link:
                lines.append(f"  {link}")
            if summary:
                lines.append(f"  {summary}")
        lines.append("")
    return "\n".join(lines).strip()


# ---------------------------
# Send via Resend
# ---------------------------
def send_via_resend(html: str, plain: str | None = None) -> None:
    api_key = os.environ["RESEND_API_KEY"]
    to_email = os.environ["TO_EMAIL"]
    from_email = os.environ.get("RESEND_FROM", "AI Digest <onboarding@resend.dev>")
    reply_to = os.environ.get("REPLY_TO")  # optional
    subject = "AI & AI Security — Daily Digest"

    payload = {
        "from": from_email,
        "to": [to_email],
        "subject": subject,
        "html": html,
    }
    if plain:
        payload["text"] = plain
    if reply_to:
        payload["reply_to"] = reply_to

    resp = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {api_key}",
                 "Content-Type": "application/json"},
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Resend error {resp.status_code}: {resp.text}")


# ---------------------------
# Main
# ---------------------------
def main() -> int:
    try:
        max_per_source = int(os.getenv("MAX_PER_SOURCE", "10"))
    except ValueError:
        max_per_source = 10

    cfg = load_config("config.yaml")
    buckets = fetch_all(cfg)
    html = render_html(buckets, max_per_source=max_per_source)
    plain = render_plaintext(buckets, max_per_source=max_per_source)

    # If no API key set, print HTML to stdout for local preview
    if not os.getenv("RESEND_API_KEY"):
        sys.stderr.write("[info] RESEND_API_KEY not set; printing HTML to stdout.\n")
        print(html)
        return 0

    send_via_resend(html=html, plain=plain)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
