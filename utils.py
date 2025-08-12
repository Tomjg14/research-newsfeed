import os
import smtplib
import ssl
from email.mime.text import MIMEText
from datetime import datetime, timezone
from typing import Dict, Any
import yaml
from dateutil import tz

def load_config(path: str = "config.yaml") -> Dict[str, Any]:
    if not os.path.exists(path):
        return {"sources": {}}
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def utc_now() -> datetime:
    return datetime.now(timezone.utc)

def to_ams(dt_utc: datetime) -> datetime:
    # Europe/Amsterdam display helper (no hard dependency on zoneinfo aliases in CI)
    return dt_utc.astimezone(tz.gettz("Europe/Amsterdam"))

def humanize_dt(dt_utc: datetime) -> str:
    d = to_ams(dt_utc)
    return d.strftime("%Y-%m-%d %H:%M")

def send_email_html(
    to_email: str,
    subject: str,
    html: str,
    from_email: str = None,
) -> None:
    host = os.environ.get("SMTP_HOST", "")
    port = int(os.environ.get("SMTP_PORT", "587"))
    user = os.environ.get("SMTP_USER", "")
    pwd = os.environ.get("SMTP_PASS", "")
    from_email = from_email or os.environ.get("FROM_EMAIL", user or "no-reply@example.com")

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = from_email
    msg["To"] = to_email

    context = ssl.create_default_context()
    with smtplib.SMTP(host, port) as server:
        server.starttls(context=context)
        if user:
            server.login(user, pwd)
        server.send_message(msg)
