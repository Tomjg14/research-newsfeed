# sources/hackernoon.py
import requests
import feedparser
from bs4 import BeautifulSoup
from datetime import timezone
from dateutil import parser as dateparser
from utils import any_keyword_match, none_keyword_match, is_recent

DEFAULT_FEED = "https://hackernoon.com/feed"
UA = {"User-Agent": "AI-Research-Feed/1.0 (+https://example.com)"}

def _effective_keywords(config, global_filters, key):
    if key in config:
        return config.get(key) or []
    return global_filters.get(key, []) or []

def _clean_html_to_text(html):
    if not html:
        return ""
    # If it doesn't look like HTML, return as-is (prevents BS4 locator warning)
    if "<" not in html and ">" not in html:
        return html.strip()
    soup = BeautifulSoup(html, "html.parser")
    for tag in soup(["script", "style"]):
        tag.decompose()
    return " ".join(soup.get_text(separator=" ", strip=True).split())

def fetch(config, global_filters):
    feeds = config.get("feeds", [DEFAULT_FEED])
    lookback_days = int(config.get("lookback_days", global_filters.get("lookback_days", 7)))
    include_keywords = _effective_keywords(config, global_filters, "include_keywords")
    exclude_keywords = _effective_keywords(config, global_filters, "exclude_keywords")

    out = []
    seen = set()

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
            raw_summary = (
                e.get("summary")
                or (e.get("content") or [{}])[0].get("value")
                or ""
            )
            summary = _clean_html_to_text(raw_summary)

            hay = f"{title}\n{summary}"
            if include_keywords and not any_keyword_match(hay, include_keywords):
                continue
            if not none_keyword_match(hay, exclude_keywords):
                continue

            link = e.get("link", "")
            item_id = e.get("id") or link
            if item_id in seen:
                continue
            seen.add(item_id)

            authors = [{"name": a.get("name")} for a in (e.get("authors") or []) if a.get("name")]

            out.append({
                "id": item_id,
                "title": f"[Hackernoon] {title}",
                "summary": summary,
                "authors": authors,
                "published": published_dt,
                "source": "Hackernoon",
                "category": url,
                "tags": ["hackernoon"],
                "pdf": "",
                "link": link,
            })
    return out
