"""Alerts for HIGH risk reports: Slack webhook and/or email. Falls back to a log warning."""
from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
from email.message import EmailMessage

from .config import settings
from .schemas import Report

log = logging.getLogger(__name__)


def _text(report: Report, supplier_name: str) -> str:
    lines = [f":rotating_light: HIGH risk - {supplier_name} ({report.period})", report.summary]
    lines += [f"- PO {i.po_id} [{i.type}] {i.description}" for i in report.issues if i.severity == "high"]
    return "\n".join(lines)


def send_alert(report: Report, supplier_name: str) -> None:
    text = _text(report, supplier_name)
    sent = False
    if settings.slack_webhook_url:
        try:
            req = urllib.request.Request(
                settings.slack_webhook_url, data=json.dumps({"text": text}).encode(),
                headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=10).read()
            sent = True
        except Exception as e:  # noqa: BLE001
            log.error("Slack alert failed: %s: %s", type(e).__name__, e)
    if settings.smtp_host and settings.alert_email_to:
        try:
            msg = EmailMessage()
            msg["Subject"] = f"[HIGH RISK] {supplier_name} compliance report {report.period}"
            msg["From"] = settings.alert_email_from or settings.smtp_user or "agent@localhost"
            msg["To"] = settings.alert_email_to
            msg.set_content(text)
            if settings.smtp_port == 465:  # SSL from the first byte
                server = smtplib.SMTP_SSL(settings.smtp_host, 465, timeout=15)
            else:  # 587: connect, then upgrade with STARTTLS
                server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15)
                server.starttls()
            with server:
                if settings.smtp_user:
                    server.login(settings.smtp_user, settings.smtp_password or "")
                server.send_message(msg)
            sent = True
        except Exception as e:  # noqa: BLE001
            log.error("Email alert failed (%s:%s): %s: %s",
                      settings.smtp_host, settings.smtp_port, type(e).__name__, e)
    if not sent:
        log.warning("HIGH RISK alert could not be delivered (see errors above):\n%s", text)