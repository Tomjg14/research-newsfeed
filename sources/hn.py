# sources/hn.py
import requests
import feedparser
from datetime import timezone
from dateutil import parser as dateparser
from bs4 import BeautifulSoup
from utils import any_keyword_match, none_keyword_match, is_recent

DEFAULT_FEEDS = ["https://hnrss.org/frontpage"]
UA = {"User-Agent": "AI-Research-Feed/1.0 (+https://example.com)"}

def _effective_keywords(config, global_filters, key):
    # If source sets include/exclude explicitly (even []), use that; else fall back to global
    if key in config:
        return config.get(key) or []
    return global_filters.get(key, []) or []

def _clean_html_to_text(html: str) -> str:
    if not html:
        return ""
    # If it doesn't look like HTML, return as-is (prevents BS4 locator warning)
    if "<" not in html and ">" not in html:
        return html.strip()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    # Normalize whitespace
    return " ".join(soup.get_text(separator=" ", strip=True).split())

def fetch(config, global_filters):
    feeds = config.get("feeds", DEFAULT_FEEDS)
    lookback_days = int(config.get("lookback_days", global_filters.get("lookback_days", 7)))
    include_keywords = _effective_keywords(config, global_filters, "include_keywords")
    exclude_keywords = _effective_keywords(config, global_filters, "exclude_keywords")

    out, seen = [], set()

    for url in feeds:
        try:
            r = requests.get(url, headers=UA, timeout=20)
            r.raise_for_status()
            feed = feedparser.parse(r.content)
        except Exception:
            continue

        for e in feed.entries:
            published = e.get("published") or e.get("updated") or ""
            try:
                published_dt = dateparser.parse(published).astimezone(timezone.utc) if published else None
            except Exception:
                published_dt = None
            if not is_recent(published_dt, lookback_days):
                continue

            title = (e.get("title") or "").strip()

            # HN summaries often contain HTML; clean to plain text
            raw_summary = (
                e.get("summary")
                or (e.get("content") or [{}])[0].get("value")
                or ""
            )
            summary = _clean_html_to_text(raw_summary)
            # keep it short—HN summaries can be chatty
            if len(summary) > 240:
                summary = summary[:240].rsplit(" ", 1)[0] + "…"

            hay = f"{title}\n{summary}"
            if include_keywords and not any_keyword_match(hay, include_keywords):
                continue
            if not none_keyword_match(hay, exclude_keywords):
                continue

            link = e.get("link", "")              # usually article URL
            comments = getattr(e, "comments", "") # HN discussion link if present
            item_id = e.get("id") or comments or link
            if item_id in seen:
                continue
            seen.add(item_id)

            out.append({
                "id": item_id,
                "title": f"[HN] {title}",
                "summary": summary,
                "authors": [],
                "published": published_dt,
                "source": "Hacker News",
                "category": url,
                "tags": ["hn"],
                "pdf": "",
                "link": comments or link,  # prefer HN discussion if available
            })
    return out
