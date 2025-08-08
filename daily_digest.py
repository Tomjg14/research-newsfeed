import os, smtplib
from email.mime.text import MIMEText

def send_via_outlook_smtp(html, subject="AI & AI Security — Daily Digest"):
    user = os.environ["OUTLOOK_USER"]      # e.g. yourname@hotmail.nl
    pwd  = os.environ["OUTLOOK_PASSWORD"]  # see note below
    to   = os.environ.get("TO_EMAIL", user)

    msg = MIMEText(html, "html", "utf-8")
    msg["Subject"] = subject
    msg["From"] = user
    msg["To"] = to

    # Outlook/Hotmail SMTP
    with smtplib.SMTP("smtp.office365.com", 587, timeout=30) as s:
        s.ehlo()
        s.starttls()
        s.login(user, pwd)
        s.sendmail(user, [to], msg.as_string())

if __name__ == "__main__":
    # ... build html as before ...
    send_via_outlook_smtp(html)