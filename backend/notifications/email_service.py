"""SMTP escalation email sender.

Graceful no-op when SMTP is not configured. Never raises — an email failure must
not block the user response or the graph.
"""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from core.config import get_settings

logger = logging.getLogger(__name__)


def send_escalation_email(
    escalation_id: str,
    query_id: str,
    reason: str,
    query_preview: str,
) -> bool:
    """
    Send escalation notification email.
    Returns True if sent, False if skipped (SMTP not configured) or failed.
    Never raises — email failure must not block the user response.
    """
    settings = get_settings()
    if not settings.SMTP_HOST or not settings.ESCALATION_EMAIL:
        logger.info("Email not configured; escalation %s logged to DB only", escalation_id)
        return False

    subject = f"[RAG Escalation] New query requires human review — Ticket #{escalation_id[:8]}"
    body = f"""A query has been escalated for human review.

Ticket ID:    {escalation_id}
Query ID:     {query_id}
Reason:       {reason}
Query:        {query_preview}

Please review this query in the escalation dashboard and mark it resolved.
"""
    try:
        msg = MIMEMultipart()
        msg["From"] = settings.SMTP_USER
        msg["To"] = settings.ESCALATION_EMAIL
        msg["Subject"] = subject
        msg.attach(MIMEText(body, "plain"))

        with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=10) as server:
            server.ehlo()
            server.starttls()
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
            server.sendmail(settings.SMTP_USER, settings.ESCALATION_EMAIL, msg.as_string())

        logger.info("Escalation email sent for ticket %s", escalation_id[:8])
        return True
    except Exception as exc:
        logger.warning("Escalation email failed (non-fatal): %s", exc)
        return False
