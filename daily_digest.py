#!/usr/bin/env python3
"""
Daily digest generator + Outlook/Hotmail SMTP sender.

Env vars (set in GitHub Actions 'env:' with repo Secrets):
  OUTLOOK_USER       e.g. yourname@hotmail.nl
  OUTLOOK_PASSWORD   your Outlook/Microsoft password (or app password)
  TO_EMAIL           recipient (defaults to OUTLOOK_USER if unset)
  MAX_PER_SOURCE     optional, default 10  (items per source)
"""

from __future__ import annotations
import os
import sys
import smtplib
import datetime as dt
from email.mime.text import MIMEText
from typing import Dict, List, Tuple, Any

import yaml

# --- Import your existing fetchers (from the v2/v3 project) ---
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
    """Return a dict of {source_name: [entries...]}."""
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

    # Sort each source newest->oldest; entries provide 'published' or None
    for name, items in buckets.items():
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
            # Escape minimal risky chars in title
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
    """Plain-text fallback body."""
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
# Email via Outlook/Hotmail SMTP
# ---------------------------
def send_via_outlook_smtp(
    html: str,
    plain: str | None = None,
    subject: str = "AI & AI Security — Daily Digest",
    retry: int = 1,
) -> None:
    user = os.environ["OUTLOOK_USER"]          # yourname@hotmail.nl
    pwd = os.environ["OUTLOOK_PASSWORD"]       # normal or app password
    to_addr = os.environ.get("TO_EMAIL", user)

    # Simple HTML-only message (most clients handle fine). If you want multipart/alternative,
    # you can build it—but this keeps deps minimal.
    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to_addr

    # Send with STARTTLS
    last_err: Exception | None = None
    for attempt in range(retry + 1):
        try:
            with smtplib.SMTP("smtp.office365.com", 587, timeout=30) as s:
                s.ehlo()
                s.starttls()
                s.login(user, pwd)
                s.sendmail(user, [to_addr], msg.as_string())
            return
        except Exception as e:
            last_err = e
            if attempt < retry:
                continue
            raise


# ---------------------------
# Main
# ---------------------------
def main() -> int:
    # Read per-source cap from env if provided
    try:
        max_per_source = int(os.getenv("MAX_PER_SOURCE", "10"))
    except ValueError:
        max_per_source = 10

    cfg = load_config("config.yaml")
    buckets = fetch_all(cfg)
    html = render_html(buckets, max_per_source=max_per_source)
    plain = render_plaintext(buckets, max_per_source=max_per_source)

    # If running locally without env vars, print HTML so you can eyeball it
    missing = [k for k in ("OUTLOOK_USER", "OUTLOOK_PASSWORD") if not os.getenv(k)]
    if missing:
        sys.stderr.write(
            f"[info] Missing env vars {missing}; printing HTML to stdout instead.\n"
            f"Set OUTLOOK_USER/OUTLOOK_PASSWORD/TO_EMAIL to send via Outlook SMTP.\n"
        )
        print(html)
        return 0

    # Send the email
    send_via_outlook_smtp(html=html, plain=plain, retry=1)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
