import os, yaml, datetime
from sources import arxiv as src_arxiv
from sources import openreview as src_openreview
from sources import acl as src_acl
from sources import reddit as src_reddit

def fetch_all(cfg):
    gf = {
        "lookback_days": int(cfg.get("lookback_days", 7)),
        "include_keywords": cfg.get("include_keywords", []),
        "exclude_keywords": cfg.get("exclude_keywords", []),
        "priority_authors": [a.lower() for a in cfg.get("priority_authors", [])],
    }
    scfg = cfg.get("sources", {})
    buckets, results = {}, []

    def add(name, arr):
        buckets[name] = arr
        results.extend(arr)

    if scfg.get("arxiv", {}).get("enabled", True):
        add("arXiv", src_arxiv.fetch(scfg.get("arxiv", {}), gf))
    if scfg.get("openreview", {}).get("enabled", True):
        add("OpenReview", src_openreview.fetch(scfg.get("openreview", {}), gf))
    if scfg.get("acl", {}).get("enabled", True):
        add("ACL Anthology", src_acl.fetch(scfg.get("acl", {}), gf))
    if scfg.get("reddit", {}).get("enabled", True):
        add("Reddit", src_reddit.fetch(scfg.get("reddit", {}), gf))

    results.sort(key=lambda x: x.get("published") or datetime.datetime.min, reverse=True)
    return buckets

def render_html(buckets, max_per_source=10):
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    parts = [f"<h2>AI & AI Security — Daily Digest ({today})</h2>"]
    for name, items in buckets.items():
        if not items:
            continue
        parts.append(f"<h3>{name} ({min(len(items), max_per_source)})</h3><ul>")
        for it in items[:max_per_source]:
            title = it.get("title", "")
            link = it.get("pdf") or it.get("link", "")
            summary = (it.get("summary") or "").strip()
            if len(summary) > 280:
                summary = summary[:280].rsplit(" ", 1)[0] + "…"
            parts.append(f"<li><a href='{link}'>{title}</a><br><small>{summary}</small></li>")
        parts.append("</ul>")
    return "\n".join(parts)

def send_sendgrid(html):
    from sendgrid import SendGridAPIClient
    from sendgrid.helpers.mail import Mail
    msg = Mail(
        from_email=os.environ.get("FROM_EMAIL") or os.environ["TO_EMAIL"],
        to_emails=os.environ["TO_EMAIL"],
        subject="AI & AI Security — Daily Digest",
        html_content=html,
    )
    SendGridAPIClient(os.environ["SENDGRID_API_KEY"]).send(msg)

if __name__ == "__main__":
    with open("config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    buckets = fetch_all(cfg)
    html = render_html(buckets, max_per_source=int(os.getenv("MAX_PER_SOURCE", "10")))
    send_sendgrid(html)
