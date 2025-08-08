import feedparser
from dateutil import parser as dateparser
from datetime import timezone
from utils import any_keyword_match, none_keyword_match, is_recent

def fetch(config, global_filters):
    feeds = config.get("feeds", [])
    lookback_days = int(global_filters.get("lookback_days", 7))
    include_keywords = global_filters.get("include_keywords", [])
    exclude_keywords = global_filters.get("exclude_keywords", [])

    entries = []
    for url in feeds:
        feed = feedparser.parse(url)
        for e in feed.entries:
            published = e.get("published", e.get("updated", ""))
            try:
                published_dt = dateparser.parse(published).astimezone(timezone.utc)
            except Exception:
                published_dt = None

            title = e.get("title","").strip()
            summary = (e.get("summary","") or "").strip()
            hay = f"{title}\n{summary}"

            if not is_recent(published_dt, lookback_days):
                continue
            if include_keywords and not any_keyword_match(hay, include_keywords):
                continue
            if not none_keyword_match(hay, exclude_keywords):
                continue

            link = e.get("link","")
            authors = [{"name": a.get("name")} for a in e.get("authors", [])] if e.get("authors") else []

            entries.append({
                "id": e.get("id", link),
                "title": title,
                "summary": summary,
                "authors": authors,
                "published": published_dt,
                "source": "ACL Anthology",
                "category": url,
                "tags": ["acl"],
                "pdf": "",
                "link": link,
            })
    return entries
