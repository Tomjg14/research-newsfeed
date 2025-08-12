import os
import streamlit as st
from datetime import datetime, timedelta, timezone
from typing import List, Dict
from db import get_engine, ensure_schema, upsert_user, get_user, set_user_sources, get_user_sources, set_user_hours_default, get_user_hours_default, list_supported_sources
from utils import load_config, utc_now, humanize_dt
from digest_helpers import fetch_items, render_digest_html, filter_items_by_hours

st.set_page_config(page_title="Research Newsfeed", page_icon="📰", layout="wide")

# --- App state / init ---
engine = get_engine()
ensure_schema(engine)
cfg = load_config()

st.title("📰 Research Newsfeed")
st.caption("Subscribe to a daily/weekly digest of new research items. Choose your sources and time window.")

# --- Auth-lite (email only) ---
st.subheader("1) Sign in or create your subscription")
email = st.text_input("Your email", placeholder="you@example.com")

col_a, col_b = st.columns([1,1])
with col_a:
    if st.button("Sign in / Create"):
        if not email or "@" not in email:
            st.error("Please enter a valid email.")
        else:
            user = upsert_user(engine, email=email)
            st.success(f"Signed in as {user.email}")
with col_b:
    if st.button("Sign out"):
        email = ""
        st.experimental_rerun()

if not email:
    st.info("Enter your email to continue.")
    st.stop()

user = get_user(engine, email=email)
if not user:
    st.error("Could not load your account. Try again.")
    st.stop()

# --- Preferences ---
st.subheader("2) Choose your sources")
supported = list_supported_sources(cfg)
current_sources = set(get_user_sources(engine, user_id=user.id))
sel = st.multiselect(
    "Pick sources",
    options=supported,
    default=sorted(current_sources) if current_sources else supported
)
if st.button("Save sources"):
    set_user_sources(engine, user.id, sel)
    st.success("Saved your sources.")

st.markdown("---")

# --- Time window controls ---
st.subheader("3) Time window")
default_hours = get_user_hours_default(engine, user.id) or 24
mode = st.segmented_control("Window type", options=["Hours", "Days"], default="Hours")
if mode == "Hours":
    hours = st.slider("Include items from the last X hours", 1, 168, default_hours)
    days = None
else:
    days = st.slider("Include items from the last X days", 1, 14, max(1, default_hours // 24))
    hours = days * 24

if st.button("Save default window"):
    set_user_hours_default(engine, user.id, hours)
    st.success(f"Saved your default window: last {hours} hours.")

st.markdown("---")

# --- Preview ---
st.subheader("4) Preview your digest")
with st.status("Fetching items...", expanded=False):
    items_by_source = fetch_items(cfg, sources=sel or supported, limit_per_source=cfg.get("ui_preview_limit", 50))
    filtered = filter_items_by_hours(items_by_source, hours=hours)
    html = render_digest_html(filtered, title="Your preview digest", now=utc_now())

st.components.v1.html(html, height=900, scrolling=True)

st.markdown("---")
st.caption("Tip: Deploy this on Streamlit Community Cloud (free). Your email digest runs via GitHub Actions.")
