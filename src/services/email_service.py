"""Phase 11: sends the newsletter over SMTP (stdlib only, no extra dependency)."""
import logging
import smtplib
import ssl
from email.message import EmailMessage

from src.config import Settings

log = logging.getLogger(__name__)


class EmailError(Exception):
    pass


class EmailService:
    def __init__(
        self, host: str, port: int, username: str, password: str,
        sender: str, recipients: list[str], timeout: float = 30.0,
    ) -> None:
        if not (username and password and recipients):
            raise EmailError("Email is not configured (need SMTP_USERNAME, SMTP_PASSWORD, EMAIL_TO)")
        self.host, self.port = host, port
        self.username, self.password = username, password
        self.sender, self.recipients = sender or username, recipients
        self.timeout = timeout

    @classmethod
    def from_settings(cls, s: Settings) -> "EmailService":
        return cls(s.smtp_host, s.smtp_port, s.smtp_username, s.smtp_password, s.sender, s.recipients)

    def send(self, subject: str, html: str, text: str) -> None:
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.sender
        msg["To"] = ", ".join(self.recipients)
        msg.set_content(text)  # plain-text part first, HTML as the preferred alternative
        msg.add_alternative(html, subtype="html")

        context = ssl.create_default_context()
        try:
            if self.port == 465:
                server = smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout, context=context)
            else:
                server = smtplib.SMTP(self.host, self.port, timeout=self.timeout)
            with server:
                if self.port != 465:
                    server.starttls(context=context)
                server.login(self.username, self.password)
                server.send_message(msg)
        except smtplib.SMTPAuthenticationError as exc:
            raise EmailError("SMTP login rejected (for Gmail, use an App Password, not your normal password)") from exc
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailError(f"Could not send email: {exc}") from exc
        log.info("Newsletter sent to %d recipient(s)", len(self.recipients))
