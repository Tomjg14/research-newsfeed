import feedparser
from dateutil import parser as dateparser
from datetime import timezone
from bs4 import BeautifulSoup
from utils import any_keyword_match, none_keyword_match, is_recent

REDDIT_RSS = "https://www.reddit.com/r/{sub}/new/.rss"

def clean_html_to_text(html):
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script","style"]):
        tag.decompose()
    text = soup.get_text(separator=" ", strip=True)
    return " ".join(text.split())

def preview(text, max_chars=300):
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    return text[:max_chars].rsplit(" ", 1)[0] + "…"

def fetch(config, global_filters):
    subs = config.get("subreddits", [])
    lookback_days = int(global_filters.get("lookback_days", 7))
    include_keywords = global_filters.get("include_keywords", [])
    exclude_keywords = list(set((global_filters.get("exclude_keywords", []) or []) + (config.get("exclude_keywords", []) or [])))
    extra_include = config.get("include_keywords", [])
    include_keywords = list(set((include_keywords or []) + (extra_include or [])))
    preview_chars = int(config.get("preview_chars", 300))

    entries = []
    for s in subs:
        url = REDDIT_RSS.format(sub=s)
        feed = feedparser.parse(url, agent="Mozilla/5.0 (AI Research Feed)")
        for e in feed.entries:
            published = e.get("published", e.get("updated", ""))
            try:
                published_dt = dateparser.parse(published).astimezone(timezone.utc)
            except Exception:
                published_dt = None

            title = (e.get("title", "") or "").strip()
            raw_html = ""
            if "content" in e and e.content:
                raw_html = " ".join(c.get("value","") for c in e.content if isinstance(c, dict))
            else:
                raw_html = e.get("summary","") or ""
            cleaned = clean_html_to_text(raw_html)
            short = preview(cleaned, preview_chars)

            hay = f"{title}\n{cleaned}"
            if not is_recent(published_dt, lookback_days): 
                continue
            if include_keywords and not any_keyword_match(hay, include_keywords):
                continue
            if not none_keyword_match(hay, exclude_keywords):
                continue

            link = e.get("link","")
            entries.append({
                "id": e.get("id", link),
                "title": f"[r/{s}] {title}",
                "summary": short,
                "fulltext": cleaned,
                "authors": [],
                "published": published_dt,
                "source": "Reddit",
                "category": s,
                "tags": ["reddit"],
                "pdf": "",
                "link": link,
            })
    return entries
