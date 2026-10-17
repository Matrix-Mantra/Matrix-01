"""Send the report PDF by email over SMTP (or save it to MAIL_OUTBOX for local testing).

Nothing is stored: the PDF is built for the email, sent, and discarded.
"""

from __future__ import annotations

import re
import smtplib
import ssl
import time
from email.message import EmailMessage
from pathlib import Path

from . import config

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


class MailNotConfigured(RuntimeError):
    pass


def valid_email(email: str) -> bool:
    return len(email) <= 254 and bool(EMAIL_RE.match(email))


def configured() -> bool:
    return bool(config.SMTP_HOST or config.MAIL_OUTBOX)


TEXT = {
    "en": {
        "subject": "Your hospital guide: {title}",
        "body": "Hello {name},\n\nYour hospital guide from Matrix is attached as a PDF.\n\n{title}\n{urgency}\n\n"
                "{dept_label}: {department}\n{where}\n"
                "{disclaimer}\n\n"
                "— Matrix · hospitalsofnepal.com\n",
        "where": "Where to go: {hospital}\nDirections: {url}\n",
        "dept": "Department to visit", "animal": "Animal", "vets": "Find vets near you: {url}\n",
    },
    "ne": {
        "subject": "तपाईंको अस्पताल गाइड: {title}",
        "body": "नमस्ते {name},\n\nMatrix बाट तपाईंको अस्पताल गाइड PDF मा संलग्न छ।\n\n{title}\n{urgency}\n\n"
                "{dept_label}: {department}\n{where}\n"
                "{disclaimer}\n\n"
                "— Matrix · hospitalsofnepal.com\n",
        "where": "कहाँ जाने: {hospital}\nबाटो: {url}\n",
        "dept": "जाने विभाग", "animal": "जनावर", "vets": "नजिकका पशु चिकित्सक: {url}\n",
    },
}


def build_message(to: str, name: str, report: dict, pdf_bytes: bytes) -> EmailMessage:
    tx = TEXT["ne" if report.get("lang") == "ne" else "en"]
    top = (report.get("hospitals") or [None])[0]
    hospital = top and ((top.get("name_ne") if report.get("lang") == "ne" else None) or top.get("name"))
    where = tx["where"].format(hospital=hospital, url=top.get("directions_url", "")) if top else ""
    animal = report.get("kind") == "animal"
    if animal and report.get("vet_search_url"):
        where += tx["vets"].format(url=report["vet_search_url"])
    msg = EmailMessage()
    msg["Subject"] = tx["subject"].format(title=report.get("title", ""))[:200]
    msg["From"] = f"Matrix <{config.MAIL_FROM}>" if config.MAIL_FROM else "Matrix <noreply@localhost>"
    msg["To"] = to
    msg.set_content(tx["body"].format(name=name, title=report.get("title", ""), urgency=report.get("urgency_text", ""),
                                      dept_label=tx["animal"] if animal else tx["dept"],
                                      department=report.get("animal_label" if animal else "department_label", ""),
                                      where=where, disclaimer=report.get("disclaimer", "")))
    day = str(report.get("generated_at", ""))[:10] or time.strftime("%Y-%m-%d")
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=f"hospital-guide-{day}.pdf")
    return msg


def send(msg: EmailMessage) -> bool:
    """Send the message. Returns True if it was really sent, False if it was only saved to MAIL_OUTBOX."""
    if config.SMTP_HOST:
        ctx = ssl.create_default_context()
        if config.SMTP_PORT == 465:
            with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, context=ctx, timeout=30) as s:
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        else:
            with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as s:
                s.starttls(context=ctx)
                if config.SMTP_USER:
                    s.login(config.SMTP_USER, config.SMTP_PASSWORD)
                s.send_message(msg)
        return True
    if config.MAIL_OUTBOX:
        out = Path(config.MAIL_OUTBOX)
        out.mkdir(parents=True, exist_ok=True)
        (out / f"{time.time():.6f}.eml").write_bytes(msg.as_bytes())
        return False
    raise MailNotConfigured("Email is not set up on this server.")
