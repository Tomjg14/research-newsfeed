# digest_helpers.py
from daily_digest import load_config, fetch_all, render_html, render_plaintext, send_via_resend
import os

def build_digest(max_per_source=10):
    cfg = load_config("config.yaml")
    buckets = fetch_all(cfg)
    html = render_html(buckets, max_per_source=max_per_source)
    plain = render_plaintext(buckets, max_per_source=max_per_source)
    return html, plain

def get_secret(name, default=None):
    # Prefer Streamlit secrets if available; fall back to env
    try:
        import streamlit as st
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.getenv(name, default)

def has_email_credentials():
    return bool(get_secret("RESEND_API_KEY") and get_secret("TO_EMAIL"))
