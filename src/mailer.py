"""Send the digest as an HTML email over Gmail SMTP.

Requires a Gmail *app password* (not your normal password), which needs 2-Step
Verification enabled on the account. See the README for setup.
"""

from __future__ import annotations

import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465  # implicit TLS (SSL)


def _plain_text_fallback(subject: str) -> str:
    return (
        f"{subject}\n\n"
        "This is the Hacker News Daily digest. Your email client does not "
        "support HTML; please view it in an HTML-capable client."
    )


def send_email(
    *,
    username: str,
    app_password: str,
    recipients: list[str],
    subject: str,
    html_body: str,
) -> None:
    message = MIMEMultipart("alternative")
    message["Subject"] = subject
    message["From"] = f"Hacker News Daily <{username}>"
    message["To"] = ", ".join(recipients)

    message.attach(MIMEText(_plain_text_fallback(subject), "plain", "utf-8"))
    message.attach(MIMEText(html_body, "html", "utf-8"))

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, timeout=30) as server:
        server.login(username, app_password)
        server.sendmail(username, recipients, message.as_string())
