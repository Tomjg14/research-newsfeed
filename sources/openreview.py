import requests
from datetime import datetime, timezone
from utils import any_keyword_match, none_keyword_match, is_recent

API = "https://api.openreview.net/notes"

def fetch(config, global_filters):
    venues = config.get("venues", [])
    limit = int(config.get("limit_per_venue", 75))
    lookback_days = int(global_filters.get("lookback_days", 7))
    include_keywords = global_filters.get("include_keywords", [])
    exclude_keywords = global_filters.get("exclude_keywords", [])

    out = []
    for venue in venues:
        params = {
            "details": "replyCount,writable",
            "limit": str(limit),
            "sort": "tmdate:desc",
            "content.venue": venue
        }
        try:
            r = requests.get(API, params=params, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue

        for n in data.get("notes", []):
            content = n.get("content", {}) or {}
            title = (content.get("title") or "").strip()
            abstract = (content.get("abstract") or "").strip()
            tmdate = n.get("tmdate") or n.get("mdate") or n.get("cdate")
            published_dt = None
            if tmdate:
                try:
                    published_dt = datetime.fromtimestamp(int(tmdate)/1000, tz=timezone.utc)
                except Exception:
                    published_dt = None

            if not is_recent(published_dt, lookback_days):
                continue

            hay = f"{title}\n{abstract}"
            if include_keywords and not any_keyword_match(hay, include_keywords):
                continue
            if not none_keyword_match(hay, exclude_keywords):
                continue

            authors = [{"name": a} for a in (content.get("authors") or [])]
            forum = n.get("forum") or n.get("id")
            link = f"https://openreview.net/forum?id={forum}" if forum else "https://openreview.net/"
            out.append({
                "id": n.get("id"),
                "title": title,
                "summary": abstract,
                "authors": authors,
                "published": published_dt,
                "source": "OpenReview",
                "category": venue,
                "tags": ["openreview"],
                "pdf": "",
                "link": link,
            })
    return out
