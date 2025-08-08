# Add at top:
import requests
from dateutil import parser as dateparser
from datetime import timezone
from utils import any_keyword_match, none_keyword_match, is_recent

API = "https://www.reddit.com/r/{sub}/new.json?limit={limit}"  # unauth max ~100

def fetch(config, global_filters):
    subs = config.get("subreddits", [])
    lookback_days = int(global_filters.get("lookback_days", 7))
    include_keywords = list(set((global_filters.get("include_keywords") or []) + (config.get("include_keywords") or [])))
    exclude_keywords = list(set((global_filters.get("exclude_keywords") or []) + (config.get("exclude_keywords") or [])))
    preview_chars = int(config.get("preview_chars", 300))
    per_sub_limit = int(config.get("max_results_per_subreddit", 100))

    headers = {"User-Agent": "AI-Research-Feed/1.0 (+your email)"}
    out = []

    for s in subs:
        url = API.format(sub=s, limit=min(100, per_sub_limit))
        try:
            r = requests.get(url, headers=headers, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception:
            continue

        for child in (data.get("data", {}) or {}).get("children", []):
            d = child.get("data", {}) or {}
            title = (d.get("title") or "").strip()
            selftext = (d.get("selftext") or "").strip()
            link = "https://www.reddit.com" + d.get("permalink","")
            created_utc = d.get("created_utc")
            published_dt = None
            if created_utc:
                try:
                    from datetime import datetime, timezone
                    published_dt = datetime.fromtimestamp(float(created_utc), tz=timezone.utc)
                except Exception:
                    pass

            # lookback + keyword filters
            hay = f"{title}\n{selftext}"
            if not is_recent(published_dt, lookback_days):
                continue
            if include_keywords and not any_keyword_match(hay, include_keywords):
                continue
            if not none_keyword_match(hay, exclude_keywords):
                continue

            # preview
            text = (selftext or "").replace("\r"," ").replace("\n"," ")
            if len(text) > preview_chars:
                text = text[:preview_chars].rsplit(" ",1)[0] + "…"

            out.append({
                "id": d.get("id", link),
                "title": f"[r/{s}] {title}",
                "summary": text,
                "fulltext": selftext,
                "authors": [{"name": d.get("author")}],
                "published": published_dt,
                "source": "Reddit",
                "category": s,
                "tags": ["reddit"],
                "pdf": "",
                "link": link,
            })
    return out
