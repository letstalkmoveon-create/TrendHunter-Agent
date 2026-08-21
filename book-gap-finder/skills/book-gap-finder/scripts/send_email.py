#!/usr/bin/env python3
"""
Sends a rendered report.html as an email via Resend's HTTPS API.

Switched from Gmail SMTP: Claude Code's cloud sandbox only proxies HTTP/HTTPS
traffic, so raw SMTP socket connections (smtplib) hang indefinitely there even
with full network access. Resend uses a plain HTTPS POST, which works fine
through that proxy.

Requires env var:
    RESEND_API_KEY — from https://resend.com/api-keys

Optional env var:
    RESEND_FROM — sender address (default: "onboarding@resend.dev", Resend's
                  shared test sender). Without a verified domain on your
                  Resend account, onboarding@resend.dev can only send to the
                  email address your Resend account itself is registered
                  under — that's a Resend-side restriction, not something
                  this script can bypass. Verify a domain in the Resend
                  dashboard to send to arbitrary recipients from your own
                  address.

--to is required and has no default on purpose: this script sends real email
to real inboxes, and nothing here should be able to do that by accident.
"""

import argparse
import json
import os
import sys
from pathlib import Path

try:
    import requests
except ImportError:
    sys.exit("Missing dependency 'requests'. Install it with:\n    pip install requests")

RESEND_API_URL = "https://api.resend.com/emails"
REQUEST_TIMEOUT = 30


class ConfigError(Exception):
    pass


def _require_env(name, help_text):
    val = os.environ.get(name)
    if not val:
        raise ConfigError(f"Missing environment variable {name}. {help_text}")
    return val


def send_email(to_addrs, subject, html_body, plain_fallback=None):
    api_key = _require_env(
        "RESEND_API_KEY",
        "Get one at https://resend.com/api-keys (free tier is enough for this).",
    )
    from_addr = os.environ.get("RESEND_FROM", "onboarding@resend.dev")

    payload = {
        "from": from_addr,
        "to": to_addrs,
        "subject": subject,
        "html": html_body,
        "text": plain_fallback or "This report requires an HTML-capable email client to view.",
    }

    resp = requests.post(
        RESEND_API_URL,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        data=json.dumps(payload),
        timeout=REQUEST_TIMEOUT,
    )

    if resp.status_code == 401:
        raise ConfigError("RESEND_API_KEY was rejected (401). Double-check the key value.")
    if resp.status_code == 403:
        raise RuntimeError(
            f"Resend rejected the send (403): {resp.text}. This usually means the 'from' "
            f"address ({from_addr}) isn't allowed to send to one of the recipients — "
            "onboarding@resend.dev can only send to the email your Resend account is "
            "registered under, unless you've verified your own domain."
        )
    if not resp.ok:
        raise RuntimeError(f"Resend API error {resp.status_code}: {resp.text}")


def main(argv=None):
    p = argparse.ArgumentParser(description="Email a rendered report.html via Resend's HTTPS API.")
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
    except (ConfigError, RuntimeError) as e:
        sys.exit(str(e))

    print(f"Sent to: {', '.join(to_addrs)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
