from __future__ import annotations

import mimetypes
import smtplib
from email import encoders
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path

from .config import Settings
from .models import SendResult


class EmailSender:
    def __init__(self, settings: Settings, logger) -> None:
        self.settings = settings
        self.logger = logger

    def send_text(self, subject: str, text: str) -> SendResult:
        return self.send_text_with_attachments(subject=subject, text=text, attachments=None)

    def send_text_with_attachments(
        self,
        subject: str,
        text: str,
        attachments: list[str] | None = None,
        html: str | None = None,
    ) -> SendResult:
        cfg = self.settings.email
        if not cfg.enabled:
            return SendResult(status="skipped", response="email.disabled=true")

        username = self.settings.email_username
        password = self.settings.email_password
        sender = self.settings.email_from or username
        recipients = self.settings.email_to
        if not username or not password:
            return SendResult(status="failed", response="missing EMAIL_SMTP_USERNAME/EMAIL_SMTP_PASSWORD")
        if not sender:
            return SendResult(status="failed", response="missing EMAIL_FROM")
        if not recipients:
            return SendResult(status="failed", response="missing EMAIL_TO")

        msg = MIMEMultipart("mixed")
        msg["Subject"] = subject
        msg["From"] = sender
        msg["To"] = ", ".join(recipients)
        alt = MIMEMultipart("alternative")
        alt.attach(MIMEText(text, "plain", "utf-8"))
        if isinstance(html, str) and html.strip():
            alt.attach(MIMEText(html, "html", "utf-8"))
        msg.attach(alt)

        attachment_report = []
        for path in attachments or []:
            p = Path(path)
            if not p.exists() or not p.is_file():
                attachment_report.append(f"missing:{p.name}")
                continue
            ctype, _ = mimetypes.guess_type(p.name)
            maintype, subtype = ("application", "octet-stream")
            if ctype and "/" in ctype:
                maintype, subtype = ctype.split("/", 1)
            part = MIMEBase(maintype, subtype)
            part.set_payload(p.read_bytes())
            encoders.encode_base64(part)
            part.add_header("Content-Disposition", f'attachment; filename="{p.name}"')
            msg.attach(part)
            attachment_report.append(f"attached:{p.name}")

        try:
            if cfg.use_ssl:
                with smtplib.SMTP_SSL(cfg.smtp_host, cfg.smtp_port, timeout=20) as server:
                    server.login(username, password)
                    server.sendmail(sender, recipients, msg.as_string())
            else:
                with smtplib.SMTP(cfg.smtp_host, cfg.smtp_port, timeout=20) as server:
                    server.starttls()
                    server.login(username, password)
                    server.sendmail(sender, recipients, msg.as_string())
        except Exception as exc:
            return SendResult(status="failed", response=f"email send failed: {exc}")

        extra = f", attachments={';'.join(attachment_report)}" if attachment_report else ""
        return SendResult(status="success", response=f"sent to {len(recipients)} recipient(s){extra}")
