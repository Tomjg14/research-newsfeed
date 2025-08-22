#!/usr/bin/env python3
"""
debug_sources.py — quick CLI to test fetching per source.

Usage examples:
  python debug_sources.py
  python debug_sources.py --show 3
  python debug_sources.py --source reddit openreview --show 5
  python debug_sources.py --lookback-days 7
  python debug_sources.py --include "ai, llm, security" --exclude "hiring, weekly"
"""

from __future__ import annotations
import argparse
import sys
import traceback
from datetime import datetime
from typing import Dict, Any, List

# Local imports from your project
from daily_digest import load_config
from sources import arxiv as src_arxiv
from sources import openreview as src_openreview
from sources import acl as src_acl
from sources import reddit as src_reddit
from sources import hn as src_hn
from sources import hackernoon as src_hackernoon
from utils import format_authors

SOURCE_MAP = {
    "arxiv": ("arXiv", src_arxiv.fetch),
    "openreview": ("OpenReview", src_openreview.fetch),
    "acl": ("ACL Anthology", src_acl.fetch),
    "reddit": ("Reddit", src_reddit.fetch),
    "hn": ("Hacker News", src_hn.fetch),
    "hackernoon": ("Hackernoon", src_hackernoon.fetch),
}

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Fetch and print counts per source")
    p.add_argument("--config", default="config.yaml", help="Path to config.yaml")
    p.add_argument("--source", nargs="*", choices=list(SOURCE_MAP.keys()),
                   help="Restrict to these sources (default: all enabled)")
    p.add_argument("--show", type=int, default=0,
                   help="Show the first N items per source (0 = just counts)")
    p.add_argument("--lookback-days", type=int, help="Override global lookback_days")
    p.add_argument("--include", help="Comma-separated include keywords (override)")
    p.add_argument("--exclude", help="Comma-separated exclude keywords (override)")
    return p.parse_args()

def csv_to_list(s: str | None) -> List[str]:
    if not s:
        return []
    return [x.strip() for x in s.split(",") if x.strip()]

def main() -> int:
    args = parse_args()
    cfg: Dict[str, Any] = load_config(args.config)

    # Build global filters (with optional overrides from CLI)
    global_filters = {
        "lookback_days": int(args.lookback_days if args.lookback_days is not None else cfg.get("lookback_days", 1)),
        "include_keywords": csv_to_list(args.include) if args.include is not None else (cfg.get("include_keywords") or []),
        "exclude_keywords": csv_to_list(args.exclude) if args.exclude is not None else (cfg.get("exclude_keywords") or []),
        "priority_authors": [a.lower() for a in (cfg.get("priority_authors") or [])],
    }

    src_cfg: Dict[str, Any] = cfg.get("sources", {}) or {}

    # Determine which sources to run
    wanted = args.source or list(SOURCE_MAP.keys())

    print(f"\n=== Debug fetch @ {datetime.now():%Y-%m-%d %H:%M:%S} ===")
    print(f"Global filters: lookback_days={global_filters['lookback_days']}, "
          f"include={global_filters['include_keywords'] or '(none)'}, "
          f"exclude={global_filters['exclude_keywords'] or '(none)'}\n")

    any_items = False
    for key in wanted:
        nice_name, fetch_fn = SOURCE_MAP[key]
        enabled = bool((src_cfg.get(key) or {}).get("enabled", True))
        if not enabled:
            print(f"[{nice_name}] SKIPPED (disabled in config)")
            continue

        cfg_for_src = src_cfg.get(key, {})
        try:
            items = fetch_fn(cfg_for_src, global_filters)  # type: ignore[arg-type]
        except Exception as e:
            print(f"[{nice_name}] ERROR: {e.__class__.__name__}: {e}")
            tb = traceback.TracebackException.from_exception(e)
            for line in tb.format():
                # Each line already includes file, line number, and code context
                sys.stderr.write(line)
            continue

        count = len(items)
        any_items = any_items or count > 0
        print(f"[{nice_name}] {count} item(s)")

        # Optionally show a few items
        nshow = max(0, args.show or 0)
        for i, en in enumerate(items[:nshow], 1):
            date_s = en.get("published").strftime("%Y-%m-%d %H:%M") if en.get("published") else ""
            authors = format_authors(en.get("authors"))
            title = en.get("title", "").strip()
            link = en.get("pdf") or en.get("link") or ""
            print(f"  {i:2d}. {title}")
            if date_s or authors:
                print(f"      {date_s}  {authors}")
            if link:
                print(f"      {link}")
            if en.get("summary"):
                # keep summary short for console
                s = en["summary"].replace("\n", " ").strip()
                if len(s) > 200:
                    s = s[:200].rsplit(" ", 1)[0] + "…"
                print(f"      {s}")

        if nshow and count > nshow:
            print(f"  … ({count - nshow} more)")
        print()

    if not any_items:
        print("No items returned. Consider:\n"
              "  • Increasing --lookback-days\n"
              "  • Loosening include keywords (or set source-level include_keywords: [])\n"
              "  • Verifying venue names for OpenReview\n"
              "  • Checking network/UA throttling (set a specific User-Agent for Reddit)\n")
        return 2

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
