#!/usr/bin/env python3
"""
Sends a rendered report.html as an email via Gmail SMTP with an app password.

Requires env vars:
    GMAIL_ADDRESS       — the sending Gmail account, e.g. yourname@gmail.com
    GMAIL_APP_PASSWORD  — a Gmail "app password" (Google Account > Security >
                           2-Step Verification > App passwords), NOT your real
                           account password.

--to is required and has no default on purpose: this script sends real email
to real inboxes, and nothing here should be able to do that by accident.
"""

import argparse
import os
import smtplib
import sys
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


class ConfigError(Exception):
    pass


def _require_env(name, help_text):
    val = os.environ.get(name)
    if not val:
        raise ConfigError(f"Missing environment variable {name}. {help_text}")
    return val


def send_email(to_addrs, subject, html_body, plain_fallback=None):
    gmail_address = _require_env(
        "GMAIL_ADDRESS",
        "Set it to the Gmail account you want to send from.",
    )
    app_password = _require_env(
        "GMAIL_APP_PASSWORD",
        "Generate one at https://myaccount.google.com/apppasswords "
        "(requires 2-Step Verification to be enabled on the account). "
        "This is NOT your regular Gmail password.",
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_address
    msg["To"] = ", ".join(to_addrs)

    msg.attach(MIMEText(plain_fallback or "This report requires an HTML-capable email client to view.", "plain"))
    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(gmail_address, app_password)
        server.sendmail(gmail_address, to_addrs, msg.as_string())


def main(argv=None):
    p = argparse.ArgumentParser(description="Email a rendered report.html via Gmail SMTP.")
    p.add_argument("--to", required=True, help="Comma-separated recipient email addresses.")
    p.add_argument("--subject", required=True, help="Email subject line.")
    p.add_argument("--html", required=True, help="Path to the rendered report.html file.")
    args = p.parse_args(argv)

    html_path = Path(args.html)
    if not html_path.exists():
        sys.exit(f"HTML file not found: {html_path}")
    html_body = html_path.read_text(encoding="utf-8")

    to_addrs = [a.strip() for a in args.to.split(",") if a.strip()]
    if not to_addrs:
        sys.exit("--to must contain at least one email address")

    try:
        send_email(to_addrs, args.subject, html_body)
    except ConfigError as e:
        sys.exit(str(e))
    except smtplib.SMTPAuthenticationError as e:
        sys.exit(
            f"Gmail rejected the login ({e}). Double-check GMAIL_ADDRESS and "
            "GMAIL_APP_PASSWORD — app passwords require 2-Step Verification "
            "to be enabled first."
        )

    print(f"Sent to: {', '.join(to_addrs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
