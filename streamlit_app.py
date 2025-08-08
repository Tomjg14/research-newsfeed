#!/usr/bin/env python3
# streamlit_app.py

import os
import io
from datetime import datetime
import streamlit as st

# Local imports from your project
from utils import format_authors
from sources import arxiv as src_arxiv
from sources import reddit as src_reddit
from sources import openreview as src_openreview
from sources import acl as src_acl
from sources import hn as src_hn
from sources import hackernoon as src_hackernoon

from digest_helpers import build_digest, has_email_credentials, get_secret
from daily_digest import load_config


# ---------------------------
# Page config
# ---------------------------
st.set_page_config(page_title="AI & AI Security — Morning Feed", layout="wide")

# ---------------------------
# Load config
# ---------------------------
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.yaml")
CFG = load_config(CONFIG_PATH)

ui_cfg = CFG.get("ui", {}) or {}
default_source = ui_cfg.get("default_source", "All")
show_abstract_default_default = bool(ui_cfg.get("show_abstract_default", True))
sources_cfg = CFG.get("sources", {}) or {}

# ---------------------------
# Session state defaults
# ---------------------------
if "global_filters" not in st.session_state:
    st.session_state.global_filters = {
        "lookback_days": int(CFG.get("lookback_days", 7)),
        "include_keywords": CFG.get("include_keywords", []),
        "exclude_keywords": CFG.get("exclude_keywords", []),
        "priority_authors": [a.lower() for a in CFG.get("priority_authors", [])],
    }
if "show_abstract_default" not in st.session_state:
    st.session_state.show_abstract_default = show_abstract_default_default
if "source_choice" not in st.session_state:
    st.session_state.source_choice = default_source
if "last_fetch_key" not in st.session_state:
    st.session_state.last_fetch_key = 0
if "selected_subreddit" not in st.session_state:
    st.session_state.selected_subreddit = "All"

# ---------------------------
# Sidebar
# ---------------------------
with st.sidebar:
    st.header("Filters")
    with st.form("filter_form"):
        lookback = st.number_input(
            "Lookback (days)",
            min_value=0,
            max_value=365,
            value=st.session_state.global_filters["lookback_days"],
            step=1,
        )
        include_kw_in = st.text_area(
            "Include keywords (comma-separated)",
            value=", ".join(st.session_state.global_filters["include_keywords"]),
        )
        exclude_kw_in = st.text_area(
            "Exclude keywords (comma-separated)",
            value=", ".join(st.session_state.global_filters["exclude_keywords"]),
        )
        show_abs = st.checkbox(
            "Show abstracts by default",
            value=st.session_state.show_abstract_default,
        )

        st.markdown("---")
        st.header("Sources")
        enabled = {}
        for key in ["arxiv", "openreview", "acl", "reddit", "hn", "hackernoon"]:
            src_conf = sources_cfg.get(key, {})
            enabled[key] = st.checkbox(
                f"Enable {key}",
                value=bool(src_conf.get("enabled", True)),
            )

        st.markdown("---")
        source_choice = st.selectbox(
            "View",
            options=["All", "arXiv", "OpenReview", "ACL Anthology", "Reddit", "Hacker News", "Hackernoon"],
            index=["All", "arXiv", "OpenReview", "ACL Anthology", "Reddit", "Hacker News", "Hackernoon"].index(
                st.session_state.source_choice if st.session_state.source_choice in ["All","arXiv","OpenReview","ACL Anthology","Reddit","Hacker News","Hackernoon"] else "All"
            ),
        )

        submitted = st.form_submit_button("🔄 Update")

    if submitted:
        st.session_state.global_filters = {
            "lookback_days": lookback,
            "include_keywords": [s.strip() for s in include_kw_in.split(",") if s.strip()],
            "exclude_keywords": [s.strip() for s in exclude_kw_in.split(",") if s.strip()],
            "priority_authors": st.session_state.global_filters["priority_authors"],
        }
        st.session_state.show_abstract_default = show_abs
        st.session_state.source_choice = source_choice
        st.session_state.last_fetch_key += 1

    # ---------------------------
    # Email section
    # ---------------------------
    st.markdown("---")
    st.subheader("Email")

    # Default slider value reads from config: email.max_per_source
    email_cfg = (CFG.get("email") or {})
    _cfg_lim = email_cfg.get("max_per_source")
    def _to_slider_default(v):
        # None / 0 / "" / "none"/"null" => 0 (unlimited)
        if v is None: return 0
        if isinstance(v, str) and v.strip().lower() in ("", "0", "none", "null"):
            return 0
        try:
            n = int(v)
            return max(0, n)
        except Exception:
            return 0

    default_limit = _to_slider_default(_cfg_lim)

    limit = st.slider(
        "Items per source (0 = unlimited)",
        min_value=0, max_value=200, value=default_limit, step=1,
        help="Controls how many items per source go into the email. 0 shows all."
    )

    if has_email_credentials():
        if st.button("📧 Email me today’s digest"):
            # Convert slider value to the build function’s semantics: None = unlimited
            max_per_source = None if limit == 0 else limit
            html, plain = build_digest(max_per_source=max_per_source)
            try:
                # Provide secrets to the sender via env just for this call
                os.environ["RESEND_API_KEY"] = get_secret("RESEND_API_KEY")
                os.environ["TO_EMAIL"]       = get_secret("TO_EMAIL")
                if get_secret("RESEND_FROM"): os.environ["RESEND_FROM"] = get_secret("RESEND_FROM")
                if get_secret("REPLY_TO"):    os.environ["REPLY_TO"]    = get_secret("REPLY_TO")

                from daily_digest import send_via_resend
                send_via_resend(html=html, plain=plain)
                st.success("Sent!")
            except Exception as e:
                st.error(f"Send failed: {e}")
    else:
        st.caption("Add a `.streamlit/secrets.toml` to enable one-click email.")


    # ---------------------------
    # Email diagnostics expander
    # ---------------------------
    with st.expander("🔧 Email diagnostics"):
        try:
            has_key = "RESEND_API_KEY" in st.secrets
            has_to = "TO_EMAIL" in st.secrets
            st.write({
                "secrets file found": True,
                "RESEND_API_KEY present": has_key,
                "TO_EMAIL present": has_to,
                "RESEND_FROM present": "RESEND_FROM" in st.secrets,
                "REPLY_TO present": "REPLY_TO" in st.secrets,
            })
            if not (has_key and has_to):
                st.info("Add keys to .streamlit/secrets.toml and restart the app.")
        except Exception as e:
            st.write({
                "secrets file found": False,
                "error": str(e),
            })
            st.info("Is .streamlit/secrets.toml in the project root? Did you restart Streamlit?")

# ---------------------------
# Fetching data
# ---------------------------
@st.cache_data(show_spinner=True)
def fetch_all(_sources_cfg, _global_filters, _enabled, _nonce):
    results = []
    buckets = {"arXiv": [], "OpenReview": [], "ACL Anthology": [], "Reddit": [], "Hacker News": [], "Hackernoon": []}

    if _enabled.get("arxiv", True):
        buckets["arXiv"] = src_arxiv.fetch(_sources_cfg.get("arxiv", {}), _global_filters)
        results.extend(buckets["arXiv"])
    if _enabled.get("openreview", True):
        buckets["OpenReview"] = src_openreview.fetch(_sources_cfg.get("openreview", {}), _global_filters)
        results.extend(buckets["OpenReview"])
    if _enabled.get("acl", True):
        buckets["ACL Anthology"] = src_acl.fetch(_sources_cfg.get("acl", {}), _global_filters)
        results.extend(buckets["ACL Anthology"])
    if _enabled.get("reddit", True):
        buckets["Reddit"] = src_reddit.fetch(_sources_cfg.get("reddit", {}), _global_filters)
        results.extend(buckets["Reddit"])
    if _enabled.get("hn", True):
        buckets["Hacker News"] = src_hn.fetch(_sources_cfg.get("hn", {}), _global_filters)
        results.extend(buckets["Hacker News"])
    if _enabled.get("hackernoon", True):
        buckets["Hackernoon"] = src_hackernoon.fetch(_sources_cfg.get("hackernoon", {}), _global_filters)
        results.extend(buckets["Hackernoon"])

    for k, v in buckets.items():
        print(f"[debug] {k}: {len(v)} items", flush=True)

    seen = set()
    deduped = []
    for en in results:
        key = (en.get("source"), en.get("id"))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(en)

    deduped.sort(key=lambda x: x.get("published") or datetime.min, reverse=True)
    return buckets, deduped

# ---------------------------
# Tabs
# ---------------------------
tab_feed, tab_help = st.tabs(["Feed", "Help"])

with tab_feed:
    buckets, all_entries = fetch_all(
        sources_cfg, st.session_state.global_filters, enabled, st.session_state.last_fetch_key
    )

    source_choice = st.session_state.source_choice
    entries = all_entries if source_choice == "All" else buckets.get(source_choice, [])

    if source_choice == "Reddit":
        subs = sources_cfg.get("reddit", {}).get("subreddits", [])
        sr_options = ["All"] + subs
        if st.session_state.selected_subreddit not in sr_options:
            st.session_state.selected_subreddit = "All"
        sr = st.selectbox(
            "Subreddit",
            options=sr_options,
            index=sr_options.index(st.session_state.selected_subreddit),
        )
        if sr != st.session_state.selected_subreddit:
            st.session_state.selected_subreddit = sr
        if sr != "All":
            entries = [e for e in entries if e.get("category") == sr]

    st.subheader(f"{source_choice} — {len(entries)} items")

    def to_markdown(entries_list):
        out = io.StringIO()
        out.write(f"# AI & AI Security Feed ({datetime.now():%Y-%m-%d %H:%M})\n\n")
        for i, en in enumerate(entries_list, 1):
            authors = format_authors(en.get("authors"))
            date_s = en["published"].strftime("%Y-%m-%d") if en.get("published") else ""
            out.write(f"## {i}. {en['title']}\n")
            out.write(f"- **Date:** {date_s}\n")
            out.write(f"- **Authors:** {authors}\n")
            out.write(f"- **Source:** {en.get('source','')}\n")
            if en.get("category"):
                out.write(f"- **Category:** {en['category']}\n")
            if en.get("tags"):
                out.write(f"- **Tags:** {', '.join(en['tags'])}\n")
            if en.get("pdf"):
                out.write(f"- **PDF:** {en['pdf']}\n")
            out.write(f"- **Link:** {en.get('link','')}\n\n")
            if en.get("summary"):
                out.write(f"> {en['summary']}\n\n")
        return out.getvalue().encode("utf-8")

    st.download_button(
        "⬇️ Download as Markdown",
        data=to_markdown(entries),
        file_name="ai_security_feed.md",
        mime="text/markdown",
    )

    def render_entry(en, idx):
        date_s = en["published"].strftime("%Y-%m-%d") if en.get("published") else ""
        with st.container(border=True):
            st.markdown(f"**{idx}. {en['title']}**  \n*{date_s}* — _{en.get('source','')}_")
            if en.get("authors"):
                st.markdown(f"_Authors:_ {format_authors(en['authors'])}")
            if st.session_state.show_abstract_default and en.get("summary"):
                st.write(en["summary"])
            if en.get("fulltext"):
                with st.expander("Show full post text"):
                    st.write(en["fulltext"])
            elif en.get("summary"):
                with st.expander("Abstract" if not st.session_state.show_abstract_default else "Hide abstract"):
                    st.write(en["summary"])
            cols = st.columns(3)
            link = en.get("link", "")
            pdf = en.get("pdf", "")
            with cols[0]:
                if pdf:
                    st.link_button("Open PDF", pdf)
            with cols[1]:
                if link:
                    st.link_button("Source Page", link)
            with cols[2]:
                st.write(f"**Category:** {en.get('category','')}")

    for i, en in enumerate(entries, 1):
        render_entry(en, i)

with tab_help:
    st.header("Help & Personalization")
    st.markdown(r"""
**Welcome to v3!** Here's how to customize your feed:

### Sources
- **arXiv**: Configure `categories` and `max_results_per_category` in `config.yaml`.
- **OpenReview**: Set `venues` (e.g., `\"ICLR 2025\"`, `\"NeurIPS 2024\"`). If empty results, adjust the strings to match OpenReview's **Venue** label.
- **ACL Anthology**: Add conference Atom/RSS URLs in `sources.acl.feeds`.
- **Reddit**: Add subreddits in `sources.reddit.subreddits`. Use the dropdown in the Reddit view to filter by a single subreddit.

### Filters
- **Lookback (days)**: Show only recent items (set 0 to disable).
- **Include/Exclude keywords**: Apply to titles and abstracts (or post text for Reddit).
- **Priority authors**: Always include certain authors on arXiv (edit `priority_authors` in `config.yaml`).

### Update button
Use the **🔄 Update** button after changing filters or source toggles to refresh the feed.

### Export
Use **Download as Markdown** to save the current list for reading or sharing.

### Tips
- Keep keyword lists concise for better precision.
- For OpenReview, try both current and previous year venues during conference transitions.
- For Reddit, increase `preview_chars` in `config.yaml` for longer snippets.
    """)
