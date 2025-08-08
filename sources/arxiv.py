# sources/arxiv.py  — category-based (v3-compatible) + de-dupe
import re
import feedparser
from dateutil import parser as dateparser
from datetime import timezone
from utils import any_keyword_match, none_keyword_match, is_recent

ARXIV_API = (
    "http://export.arxiv.org/api/query?"
    "search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending&max_results={maxn}"
)

def _norm_arxiv_id(raw_id: str) -> str:
    """
    arXiv ids may look like 'http://arxiv.org/abs/2401.01234v2'.
    Return '2401.01234' (strip version suffix).
    """
    if not raw_id:
        return ""
    last = raw_id.rstrip("/").rsplit("/", 1)[-1]
    return re.sub(r"v\d+$", "", last)

def fetch(config, global_filters):
    categories = config.get("categories", ["cs.AI","cs.LG","cs.CL","cs.CR"])
    maxn = int(config.get("max_results_per_category", 100))
    lookback_days = int(global_filters.get("lookback_days", 7))
    include_keywords = global_filters.get("include_keywords", [])
    exclude_keywords = global_filters.get("exclude_keywords", [])
    priority_authors = [a.lower() for a in global_filters.get("priority_authors", [])]

    all_entries = []
    seen_ids = set()  # normalized arXiv ids across categories

    for cat in categories:
        url = ARXIV_API.format(cat=cat, maxn=maxn)
        feed = feedparser.parse(url)
        for e in feed.entries:
            # Published timestamp
            published = e.get("published", e.get("updated", ""))
            try:
                published_dt = dateparser.parse(published).astimezone(timezone.utc)
            except Exception:
                published_dt = None
            if not is_recent(published_dt, lookback_days):
                continue

            # Normalize id and drop duplicates across categories
            raw_id = e.get("id", "") or e.get("link", "")
            nid = _norm_arxiv_id(raw_id)
            if nid in seen_ids:
                continue
            seen_ids.add(nid)

            # Extract PDF link
            pdf_link = None
            for link in e.get("links", []):
                href = link.get("href")
                if href and "pdf" in href:
                    pdf_link = href
                    break
            if not pdf_link:
                pdf_link = e.get("link", "")

            # Filters
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
                "id": nid,                         # use normalized id
                "title": title,
                "summary": summary,
                "authors": authors,
                "published": published_dt,
                "source": "arXiv",
                "category": cat,
                "tags": tags,
                "pdf": pdf_link,
                "link": e.get("link",""),
            })

    return all_entries
