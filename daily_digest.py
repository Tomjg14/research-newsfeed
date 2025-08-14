#!/usr/bin/env python3
"""
Daily digest generator + Resend sender (Broadcasts-ready, deduping included).

Max items per source:
- Default: unlimited
- Override via env:  MAX_PER_SOURCE (int; 0/empty/None => unlimited)
- Or via config:     email.max_per_source (same semantics)

Env vars for sending:
  RESEND_API_KEY        required for any sending
  RESEND_FROM           optional (default 'AI Digest <onboarding@resend.dev>')
  REPLY_TO              optional
  SUBJECT               optional (default 'AI & AI Security — Daily Digest')

Broadcast (preferred):
  RESEND_AUDIENCE_ID    required to send via Broadcasts (Audiences)

Legacy single-recipient fallback (kept for compatibility):
  TO_EMAIL              required if RESEND_AUDIENCE_ID is not set
"""

from __future__ import annotations
import os
import sys
import datetime as dt
from typing import Dict, List, Any, Optional

import requests
import yaml

from sources import arxiv as src_arxiv
from sources import openreview as src_openreview
from sources import acl as src_acl
from sources import reddit as src_reddit
from sources import hn as src_hn
from sources import hackernoon as src_hackernoon


# ---------------------------
# Config / Fetch
# ---------------------------
def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def fetch_all(cfg: Dict[str, Any]) -> Dict[str, List[Dict[str, Any]]]:
    """Return a dict of {source_name: [entries...]} sorted newest->oldest per source."""
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
    if (scfg.get("hn") or {}).get("enabled", True):
        buckets["Hacker News"] = src_hn.fetch(scfg.get("hn", {}), gf)
    if (scfg.get("hackernoon") or {}).get("enabled", True):
        buckets["Hackernoon"] = src_hackernoon.fetch(scfg.get("hackernoon", {}), gf)

    for items in buckets.values():
        items.sort(key=lambda x: x.get("published") or dt.datetime.min, reverse=True)

    return buckets


# ---------------------------
# De-duplication
# ---------------------------
def dedupe_buckets(buckets: Dict[str, List[Dict[str, Any]]]) -> Dict[str, List[Dict[str, Any]]]:
    """Remove duplicates inside each source bucket using (id or link) as key."""
    for name, items in list(buckets.items()):
        seen = set()
        keep: List[Dict[str, Any]] = []
        for en in items:
            key = (name, en.get("id") or en.get("link") or "")
            if key in seen:
                continue
            seen.add(key)
            keep.append(en)
        buckets[name] = keep
    return buckets


# ---------------------------
# Rendering
# ---------------------------
def _iter_limited(items: List[Dict[str, Any]], limit: Optional[int]):
    if limit is None or limit <= 0:
        yield from items
    else:
        yield from items[:limit]


def render_html(buckets: Dict[str, List[Dict[str, Any]]], max_per_source: Optional[int] = None) -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    parts: List[str] = [f"<h2>AI &amp; AI Security — Daily Digest ({today})</h2>"]
    for name, items in buckets.items():
        if not items:
            continue
        shown = len(items) if (max_per_source is None or max_per_source <= 0) else min(len(items), max_per_source)
        parts.append(f"<h3>{name} ({shown})</h3>")
        parts.append("<ul>")
        for it in _iter_limited(items, max_per_source):
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


def render_plaintext(buckets: Dict[str, List[Dict[str, Any]]], max_per_source: Optional[int] = None) -> str:
    today = dt.datetime.now().strftime("%Y-%m-%d")
    lines: List[str] = [f"AI & AI Security — Daily Digest ({today})", ""]
    for name, items in buckets.items():
        if not items:
            continue
        cap_desc = "all" if (max_per_source is None or max_per_source <= 0) else str(max_per_source)
        lines.append(f"{name} (showing {cap_desc})")
        for it in _iter_limited(items, max_per_source):
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
# Send via Resend (Broadcasts preferred)
# ---------------------------
def _resend_headers(api_key: str) -> Dict[str, str]:
    return {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }


def send_via_resend_broadcast(html: str, plain: str | None = None) -> None:
    """
    Create a Broadcast for the configured Audience and send it.
    Docs:
      - Create Broadcast: https://resend.com/docs/api-reference/broadcasts/create-broadcast
      - Send Broadcast:   https://resend.com/docs/api-reference/broadcasts/send-broadcast
    """
    api_key = os.environ["RESEND_API_KEY"]
    audience_id = os.environ["RESEND_AUDIENCE_ID"]
    from_email = os.environ.get("RESEND_FROM", "AI Digest <onboarding@resend.dev>")
    reply_to = os.environ.get("REPLY_TO")
    subject = os.environ.get("SUBJECT", "AI & AI Security — Daily Digest")

    payload = {
        "audience_id": audience_id,
        "name": subject,
        "from": from_email,
        "subject": subject,
        "html": html,
    }
    # If you prefer to control plaintext, include it; otherwise Resend will auto-generate.
    if plain is not None:
        payload["text"] = plain
    if reply_to:
        payload["reply_to"] = reply_to

    # 1) Create broadcast
    resp = requests.post(
        "https://api.resend.com/broadcasts",
        headers=_resend_headers(api_key),
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Resend Broadcast create error {resp.status_code}: {resp.text}")

    broadcast_id = resp.json().get("id")
    if not broadcast_id:
        raise RuntimeError(f"Resend Broadcast create response missing id: {resp.text}")

    # 2) Send broadcast now (use scheduledAt if you want delayed delivery)
    send_resp = requests.post(
        f"https://api.resend.com/broadcasts/{broadcast_id}/send",
        headers=_resend_headers(api_key),
        json={},  # add {"scheduledAt": "in 1 min"} if desired
        timeout=30,
    )
    if send_resp.status_code >= 300:
        raise RuntimeError(f"Resend Broadcast send error {send_resp.status_code}: {send_resp.text}")


def send_via_resend_single(html: str, plain: str | None = None) -> None:
    """Legacy single-recipient send (kept for compatibility)."""
    api_key = os.environ["RESEND_API_KEY"]
    to_email = os.environ["TO_EMAIL"]
    from_email = os.environ.get("RESEND_FROM", "AI Digest <onboarding@resend.dev>")
    reply_to = os.environ.get("REPLY_TO")
    subject = os.environ.get("SUBJECT", "AI & AI Security — Daily Digest")

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
        headers=_resend_headers(api_key),
        json=payload,
        timeout=30,
    )
    if resp.status_code >= 300:
        raise RuntimeError(f"Resend email error {resp.status_code}: {resp.text}")


# ---------------------------
# Utilities
# ---------------------------
def _parse_limit(env_val: str | None, cfg_val: Any) -> Optional[int]:
    """
    Priority: env > config > None (unlimited).
    Treat 0, "", "none", "null" (case-insensitive) as unlimited (None).
    """
    # Env first
    if env_val is not None:
        v = env_val.strip().lower()
        if v in ("", "0", "none", "null"):
            return None
        try:
            n = int(v)
            return n if n > 0 else None
        except ValueError:
            return None
    # Config next
    if cfg_val is not None:
        if isinstance(cfg_val, str):
            v = cfg_val.strip().lower()
            if v in ("", "0", "none", "null"):
                return None
            try:
                n = int(v)
                return n if n > 0 else None
            except ValueError:
                return None
        if isinstance(cfg_val, (int,)):
            return cfg_val if cfg_val > 0 else None
    # Default unlimited
    return None


# ---------------------------
# Main
# ---------------------------
def main() -> int:
    cfg = load_config("config.yaml")
    buckets = fetch_all(cfg)
    buckets = dedupe_buckets(buckets)

    # Determine limit: env > config.email.max_per_source > unlimited
    env_limit = os.getenv("MAX_PER_SOURCE")
    cfg_limit = (cfg.get("email") or {}).get("max_per_source")
    max_per_source = _parse_limit(env_limit, cfg_limit)

    html = render_html(buckets, max_per_source=max_per_source)
    plain = render_plaintext(buckets, max_per_source=max_per_source)

    if not os.getenv("RESEND_API_KEY"):
        sys.stderr.write("[info] RESEND_API_KEY not set; printing HTML to stdout.\n")
        print(html)
        return 0

    # Prefer Broadcasts if audience is configured; else fallback to single-recipient.
    if os.getenv("RESEND_AUDIENCE_ID"):
        send_via_resend_broadcast(html=html, plain=plain)
    else:
        if not os.getenv("TO_EMAIL"):
            raise RuntimeError("Neither RESEND_AUDIENCE_ID nor TO_EMAIL is set; nothing to send to.")
        send_via_resend_single(html=html, plain=plain)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
