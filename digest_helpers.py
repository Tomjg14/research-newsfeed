from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Tuple
from utils import humanize_dt, utc_now

def _safe_import(modname: str):
    try:
        return __import__(modname)
    except Exception:
        return None

# Expect each module to expose: fetch_items(config) -> List[dict]
# where item has keys: title, url, source, published (datetime, UTC), summary (optional)
MODULE_MAP = {
    "arxiv": "arxiv",
    "hackernews": "hn",
    "hackernoon": "hackernoon",
    "reddit": "reddit",
    "openreview": "openreview",
    "acl": "acl",
}

def fetch_items(config, sources: List[str], limit_per_source: int = 100) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}
    for logical in sources:
        modname = MODULE_MAP.get(logical, logical)
        mod = _safe_import(modname)
        if not mod or not hasattr(mod, "fetch_items"):
            out[logical] = []
            continue
        try:
            items = mod.fetch_items(config.get("sources", {}).get(logical, {}))
        except TypeError:
            # older signature
            items = mod.fetch_items(config)
        # normalize & limit
        normalized = []
        for it in items[:limit_per_source]:
            if not it.get("published"):
                continue
            normalized.append({
                "title": it.get("title", "(no title)"),
                "url": it.get("url"),
                "source": logical,
                "summary": it.get("summary") or it.get("abstract") or "",
                "published": it["published"],  # expect datetime aware UTC
            })
        out[logical] = normalized
    return out

def filter_items_by_hours(items_by_source: Dict[str, List[dict]], hours: int) -> Dict[str, List[dict]]:
    cutoff = utc_now() - timedelta(hours=hours)
    out = {}
    for src, items in items_by_source.items():
        out[src] = [it for it in items if it["published"] >= cutoff]
    return out

def render_digest_html(items_by_source: Dict[str, List[dict]], title: str, now: datetime) -> str:
    total = sum(len(v) for v in items_by_source.values())
    parts = [f"""<!doctype html>
<html><head><meta charset="utf-8"><title>{title}</title>
<style>
body {{ font-family: Arial, sans-serif; }}
h1 {{ margin-bottom: 0; }}
h2 {{ margin-top: 1.5rem; }}
.item {{ margin-bottom: .8rem; }}
.meta {{ color: #555; font-size: .9em; }}
</style></head><body>
<h1>{title}</h1>
<p class="meta">Generated {humanize_dt(now)} (Europe/Amsterdam). Total items: {total}</p>
"""]
    for src, items in items_by_source.items():
        if not items: 
            continue
        parts.append(f"<h2>{src} ({len(items)})</h2>")
        for it in items:
            published = humanize_dt(it["published"])
            summary = f"<div>{it['summary']}</div>" if it.get("summary") else ""
            parts.append(f"""
<div class="item">
  <a href="{it['url']}" target="_blank"><strong>{it['title']}</strong></a>
  <div class="meta">{published}</div>
  {summary}
</div>""")
    parts.append("</body></html>")
    return "\n".join(parts)
