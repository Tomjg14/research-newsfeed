# sources/arxiv.py  — category-based (v3-compatible) + de-dupe + pagination + cutoff
import calendar
from datetime import datetime, timedelta, timezone
from dateutil import parser as dateparser
import feedparser
import re
import time
from utils import any_keyword_match, none_keyword_match, is_recent

ARXIV_API = (
    "http://export.arxiv.org/api/query?"
    "search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending&start={start}&max_results={page_size}"
)

def _to_datetime_utc(struct_time_obj):
    """Convert feedparser's *_parsed to timezone-aware UTC datetime."""
    if struct_time_obj is None:
        return None
    return datetime.fromtimestamp(calendar.timegm(struct_time_obj), tz=timezone.utc)

def _norm_arxiv_id(raw_id: str) -> str:
    """
    arXiv ids may look like 'http://arxiv.org/abs/2401.01234v2'.
    Return '2401.01234' (strip version suffix).
    """
    if not raw_id:
        return ""
    last = raw_id.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"v\d+$", "", last)

def _pick_pdf_link(entry) -> str:
    # Prefer the explicit PDF link if present
    for link in entry.get("links", []):
        href = link.get("href")
        title = (link.get("title") or "").lower()
        if href and ("pdf" in href or title == "pdf"):
            return href
    # Fallback to main link
    return entry.get("link", "")

def _entry_published_dt(entry):
    # Use 'published' (initial submission) as submittedDate proxy; fallback to updated
    published = entry.get("published", entry.get("updated", ""))
    try:
        return dateparser.parse(published).astimezone(timezone.utc)
    except Exception:
        return None

def fetch(config, global_filters):
    """
    Config options (all optional):
      - categories: list[str] (default: ["cs.AI","cs.LG","cs.CL","cs.CR"])
      - max_results_per_category: int page size per request (default: 100, hard max API is 2000)
      - fetch_all: bool, paginate until exhaustion if True (default: False unless a cutoff is supplied)
      - max_pages_per_category: int safety cap while paginating (default: 1000)
      - request_pause_seconds: float polite delay between pages (default: 3.0)

    Global filters (all optional):
      - lookback_hours: int -> define cutoff; stop paging once entries are older than this
      - lookback_days: int -> same as hours but in days (ignored if lookback_hours is present)
      - include_keywords: list[str]
      - exclude_keywords: list[str]
      - priority_authors: list[str] (case-insensitive)
    """
    categories = config.get("categories", ["cs.AI", "cs.LG", "cs.CL", "cs.CR"])
    page_size = int(config.get("max_results_per_category", 100))  # per page
    page_size = max(1, min(page_size, 2000))  # API hard cap

    fetch_all = bool(config.get("fetch_all", False))
    max_pages = int(config.get("max_pages_per_category", 1000))
    pause_seconds = float(config.get("request_pause_seconds", 3.0))

    include_keywords = global_filters.get("include_keywords", [])
    exclude_keywords = global_filters.get("exclude_keywords", [])
    priority_authors = [a.lower() for a in global_filters.get("priority_authors", [])]

    # Determine a cutoff datetime in UTC if provided
    cutoff_dt = None
    if "lookback_hours" in global_filters:
        cutoff_dt = datetime.now(timezone.utc) - timedelta(hours=int(global_filters["lookback_hours"]))
    elif "lookback_days" in global_filters:
        # Keep support for the legacy days-based option
        cutoff_dt = datetime.now(timezone.utc) - timedelta(days=int(global_filters["lookback_days"]))

    all_entries = []
    seen_ids = set()  # normalized arXiv ids across categories

    for cat in categories:
        start = 0
        pages = 0
        stop_paging = False

        while True:
            url = ARXIV_API.format(cat=cat, start=start, page_size=page_size)
            feed = feedparser.parse(url)
            entries = feed.entries or []
            if not entries:
                break

            for e in entries:
                published_dt = _entry_published_dt(e)

                # If a cutoff is defined and this entry is older, we can stop (sorted descending).
                if cutoff_dt and published_dt and published_dt < cutoff_dt:
                    stop_paging = True
                    break

                # If there's no explicit cutoff but a legacy days filter was provided in the past,
                # keep honoring it via is_recent() (this is redundant when cutoff_dt is set).
                if cutoff_dt is None and "lookback_days" in global_filters:
                    if not is_recent(published_dt, int(global_filters["lookback_days"])):
                        continue

                # Normalize id and drop duplicates across categories
                raw_id = e.get("id", "") or e.get("link", "")
                nid = _norm_arxiv_id(raw_id)
                if nid in seen_ids:
                    continue
                seen_ids.add(nid)

                # Extract content
                title = (e.get("title", "") or "").strip()
                summary = (e.get("summary", "") or "").strip()
                hay = f"{title}\n{summary}"

                authors = e.get("authors", [])
                author_names = [a.get("name", "").lower() for a in authors]
                author_priority = any(a in priority_authors for a in author_names) if priority_authors else False

                include_ok = any_keyword_match(hay, include_keywords) if include_keywords else True
                exclude_ok = none_keyword_match(hay, exclude_keywords)

                if not (include_ok or author_priority):
                    continue
                if not exclude_ok:
                    continue

                tags = [t.get("term") for t in e.get("tags", []) if isinstance(t, dict) and t.get("term")]

                all_entries.append({
                    "id": nid,                         # normalized id without version
                    "title": title,
                    "summary": summary,
                    "authors": authors,
                    "published": published_dt,
                    "source": "arXiv",
                    "category": cat,
                    "tags": tags,
                    "pdf": _pick_pdf_link(e),
                    "link": e.get("link", ""),
                })

            if stop_paging:
                break

            # If fewer than a full page returned, we've exhausted results
            if len(entries) < page_size:
                break

            # If no cutoff and not explicitly fetching all, preserve legacy single-page behavior
            if cutoff_dt is None and not fetch_all:
                break

            # Advance pagination
            start += page_size
            pages += 1
            if pages >= max_pages:
                break
            time.sleep(pause_seconds)  # be polite to arXiv

    return all_entries
