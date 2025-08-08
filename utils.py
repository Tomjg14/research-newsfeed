import re
from datetime import datetime, timezone, timedelta

def normalize(s):
    return (s or "").strip()

def any_keyword_match(text, keywords):
    if not keywords:
        return True
    text_l = (text or "").lower()
    for kw in keywords:
        if kw.lower() in text_l:
            return True
    return False

def none_keyword_match(text, keywords):
    text_l = (text or "").lower()
    for kw in keywords or []:
        if kw.lower() in text_l:
            return False
    return True

def is_recent(published_dt, lookback_days):
    if not lookback_days or lookback_days <= 0:
        return True
    if not published_dt:
        return True
    now = datetime.now(timezone.utc)
    return (now - published_dt) <= timedelta(days=lookback_days)

def format_authors(authors_list):
    return ", ".join(a.get("name") for a in authors_list or [])

def ensure_list(val):
    if val is None: return []
    if isinstance(val, list): return val
    return [val]
