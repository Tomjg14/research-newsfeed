# sources/openreview.py — API v2
import openreview
from datetime import datetime, timezone, timedelta
from utils import any_keyword_match, none_keyword_match, is_recent

def _effective_keywords(config, global_filters, key):
    if key in config:
        return config.get(key) or []
    return global_filters.get(key, []) or []

def _as_text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, str):
        return v.strip()
    if isinstance(v, dict):
        # Common v2 pattern: {"value": "..."}; fallbacks just in case
        for k in ("value", "text", "content"):
            if k in v and v[k]:
                return str(v[k]).strip()
        return ""
    if isinstance(v, (list, tuple)):
        return ", ".join(_as_text(x) for x in v if x)
    return str(v).strip()

def get_first_content_text(content: dict, *keys: str) -> str:
    """Return the first present content[key] as text, handling dict/list/str forms."""
    content = content or {}
    for k in keys:
        if k in content:
            return _as_text(content[k])
    return ""

def fetch(config, global_filters):
    venues = config.get("venues", [])
    limit = int(config.get("limit_per_venue", 75))
    lookback_days = int(config.get("lookback_days", global_filters.get("lookback_days", 7)))
    include_keywords = _effective_keywords(config, global_filters, "include_keywords")
    exclude_keywords = _effective_keywords(config, global_filters, "exclude_keywords")

    client = openreview.api.OpenReviewClient(baseurl="https://api2.openreview.net")

    out = []
    for venue in venues:
        try:
            notes = client.get_all_notes(
                content={"venue": venue},
                sort="tmdate:desc",
            )
        except Exception:
            continue

        for n in notes:
            # times: prefer tmdate (ms) if present; fall back to cdate
            ts = getattr(n, "tmdate", None) or getattr(n, "mdate", None) or getattr(n, "cdate", None)
            published_dt = datetime.fromtimestamp(ts/1000, tz=timezone.utc) if ts else None
            if not is_recent(published_dt, 1):
                continue

            title = (n.content.get("title").get("value") or "")
            abstract = get_first_content_text(
                n.content,
                "abstract", "Abstract", "tl;dr", "TL;DR", "summary", "Summary"
            )
            hay = f"{title}\n{abstract}"
            if include_keywords and not any_keyword_match(hay, include_keywords):
                continue
            if not none_keyword_match(hay, exclude_keywords):
                continue

            authors = [{"name": a} for a in (n.content.get("authors") or [])]
            forum = n.forum or n.id
            link = f"https://openreview.net/forum?id={forum}"
            #html_link = n.content.get("html").get("value")
            
            out.append({
                "id": n.id,
                "title": title,
                "summary": abstract,
                "authors": authors,
                "published": published_dt,
                "source": "OpenReview",
                "category": "ICLR 2025",
                "tags": ["openreview"],
                "pdf": "",   # Optional: use client.get_pdf(n.id) if you need the binary
                "link": link,
            })
    return out
