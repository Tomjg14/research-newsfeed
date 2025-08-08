import feedparser
from dateutil import parser as dateparser
from datetime import timezone
from utils import any_keyword_match, none_keyword_match, is_recent

ARXIV_API = "http://export.arxiv.org/api/query?search_query=cat:{cat}&sortBy=submittedDate&sortOrder=descending&max_results={maxn}"

def fetch(config, global_filters):
    categories = config.get("categories", ["cs.AI","cs.LG","cs.CL","cs.CR"])
    maxn = int(config.get("max_results_per_category", 100))
    lookback_days = int(global_filters.get("lookback_days", 7))
    include_keywords = global_filters.get("include_keywords", [])
    exclude_keywords = global_filters.get("exclude_keywords", [])
    priority_authors = [a.lower() for a in global_filters.get("priority_authors", [])]

    all_entries = []
    for cat in categories:
        url = ARXIV_API.format(cat=cat, maxn=maxn)
        feed = feedparser.parse(url)
        for e in feed.entries:
            published = e.get("published", e.get("updated", ""))
            try:
                published_dt = dateparser.parse(published).astimezone(timezone.utc)
            except Exception:
                published_dt = None

            pdf_link = None
            for link in e.get("links", []):
                href = link.get("href")
                if href and "pdf" in href:
                    pdf_link = href
                    break
            if not pdf_link:
                pdf_link = e.get("link","")

            tags = [t.get("term") for t in e.get("tags", []) if isinstance(t, dict) and t.get("term")]

            authors = e.get("authors", [])
            author_names = [a.get("name","").lower() for a in authors]
            author_priority = any(a in priority_authors for a in author_names) if priority_authors else False

            hay = f'{e.get("title","")}\n{e.get("summary","")}'

            include_ok = any_keyword_match(hay, include_keywords) if include_keywords else True
            exclude_ok = none_keyword_match(hay, exclude_keywords)

            if is_recent(published_dt, lookback_days) and (include_ok or author_priority) and exclude_ok:
                all_entries.append({
                    "id": e.get("id",""),
                    "title": e.get("title","").strip(),
                    "summary": e.get("summary","").strip(),
                    "authors": authors,
                    "published": published_dt,
                    "source": "arXiv",
                    "category": cat,
                    "tags": tags,
                    "pdf": pdf_link,
                    "link": e.get("link",""),
                })
    return all_entries
