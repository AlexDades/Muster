from __future__ import annotations
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from app.config import settings


def send_email(to: str, subject: str, body: str) -> None:
    if not settings.gmail_address or not settings.gmail_app_password:
        raise RuntimeError("Gmail credentials not configured in .env")
    password = settings.gmail_app_password.replace(" ", "")
    msg = MIMEMultipart("alternative")
    msg["From"] = settings.gmail_address
    msg["To"] = to
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))
    with smtplib.SMTP("smtp.gmail.com", 587) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(settings.gmail_address, password)
        smtp.sendmail(settings.gmail_address, to, msg.as_string())
