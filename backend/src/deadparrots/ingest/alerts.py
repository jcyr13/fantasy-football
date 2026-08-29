from __future__ import annotations

import logging
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from ..config import Settings

logger = logging.getLogger(__name__)


@runtime_checkable
class EmailAlerter(Protocol):
    """Sends a plain-text alert. The runner calls this when an nflverse pull fails."""

    def send(self, subject: str, body: str) -> None: ...


@dataclass
class SmtpEmailAlerter:
    """Sends alerts over SMTP (spec: a failed nflverse pull emails John)."""

    host: str
    port: int
    sender: str
    recipient: str
    username: str = ""
    password: str = ""
    use_starttls: bool = True

    def send(self, subject: str, body: str) -> None:
        message = EmailMessage()
        message["Subject"] = subject
        message["From"] = self.sender
        message["To"] = self.recipient
        message.set_content(body)

        with smtplib.SMTP(self.host, self.port) as smtp:
            if self.use_starttls:
                smtp.starttls()
            if self.username:
                smtp.login(self.username, self.password)
            smtp.send_message(message)
        logger.info("sent nflverse failure alert to %s", self.recipient)


class LoggingEmailAlerter:
    """Fallback when SMTP is not configured: log the alert at ERROR so an
    unattended failure is still visible in the container logs.
    """

    def send(self, subject: str, body: str) -> None:
        logger.error("nflverse alert (email not configured)\n%s\n%s", subject, body)


def build_email_alerter(settings: Settings) -> EmailAlerter:
    """An SMTP alerter when host + recipient are set, else the logging fallback."""
    if settings.smtp_host and settings.alert_email_to:
        return SmtpEmailAlerter(
            host=settings.smtp_host,
            port=settings.smtp_port,
            sender=settings.alert_email_from,
            recipient=settings.alert_email_to,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_starttls=settings.smtp_starttls,
        )
    return LoggingEmailAlerter()
