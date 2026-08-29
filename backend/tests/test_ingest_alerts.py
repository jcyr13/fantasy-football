from __future__ import annotations

import logging

from deadparrots.config import Settings
from deadparrots.ingest.alerts import (
    LoggingEmailAlerter,
    SmtpEmailAlerter,
    build_email_alerter,
)


def test_build_email_alerter_falls_back_to_logging_when_smtp_unset():
    alerter = build_email_alerter(Settings(alert_email_to="john@example.com"))
    assert isinstance(alerter, LoggingEmailAlerter)


def test_build_email_alerter_returns_smtp_when_configured():
    settings = Settings(
        alert_email_to="john@example.com",
        smtp_host="smtp.example.com",
        smtp_username="u",
        smtp_password="p",
    )

    alerter = build_email_alerter(settings)

    assert isinstance(alerter, SmtpEmailAlerter)
    assert alerter.host == "smtp.example.com"
    assert alerter.recipient == "john@example.com"


def test_logging_alerter_logs_at_error(caplog):
    with caplog.at_level(logging.ERROR):
        LoggingEmailAlerter().send("subject line", "body text")

    assert "subject line" in caplog.text
    assert "body text" in caplog.text


def test_smtp_alerter_sends_a_well_formed_message(monkeypatch):
    sent = {}

    class FakeSMTP:
        def __init__(self, host, port):
            sent["host"] = host
            sent["port"] = port

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self):
            sent["starttls"] = True

        def login(self, username, password):
            sent["login"] = (username, password)

        def send_message(self, message):
            sent["message"] = message

    monkeypatch.setattr("smtplib.SMTP", FakeSMTP)

    SmtpEmailAlerter(
        host="smtp.example.com",
        port=587,
        sender="alerts@deadparrots",
        recipient="john@example.com",
        username="u",
        password="p",
    ).send("nflverse failed", "pbp: boom")

    assert sent["host"] == "smtp.example.com"
    assert sent["starttls"] is True
    assert sent["login"] == ("u", "p")
    message = sent["message"]
    assert message["To"] == "john@example.com"
    assert message["From"] == "alerts@deadparrots"
    assert message["Subject"] == "nflverse failed"
    assert message.get_content().strip() == "pbp: boom"
