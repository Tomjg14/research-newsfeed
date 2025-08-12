"""
Runs in GitHub Actions on a schedule.

For each user:
- Load user's sources (fallback to all).
- Load user's default hours (fallback 24).
- Fetch items, filter by hours, render HTML, email.

Env vars:
  SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, FROM_EMAIL (optional)
"""
import os
from db import get_engine, ensure_schema, get_user_sources, get_user_hours_default
from utils import load_config, utc_now, send_email_html
from digest_helpers import fetch_items, filter_items_by_hours, render_digest_html
from sqlalchemy import text

def list_users(engine):
    with engine.begin() as con:
        rows = con.execute(text("SELECT id, email FROM users ORDER BY id")).all()
        return [{"id": r[0], "email": r[1]} for r in rows]

def main():
    engine = get_engine()
    ensure_schema(engine)
    cfg = load_config()
    supported = sorted(list(cfg.get("sources", {}).keys()))
    users = list_users(engine)

    if not users:
        print("No users yet. Nothing to send.")
        return

    for u in users:
        srcs = get_user_sources(engine, u["id"]) or supported
        hours = get_user_hours_default(engine, u["id"]) or 24
        items_by_source = fetch_items(cfg, sources=srcs, limit_per_source=cfg.get("send_limit_per_source", 200))
        filtered = filter_items_by_hours(items_by_source, hours=hours)
        title = f"Research Newsfeed — last {hours}h"
        html = render_digest_html(filtered, title=title, now=utc_now())
        send_email_html(u["email"], subject=title, html=html)
        print(f"Sent to {u['email']} with {sum(len(v) for v in filtered.values())} items")

if __name__ == "__main__":
    main()
