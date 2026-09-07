from __future__ import annotations

import logging
from base64 import urlsafe_b64decode
from pathlib import Path
from socket import gaierror
from typing import Any

import httplib2

from komickers.exceptions import AuthenticationError, EmailError

from .utils import save_pull_list

logger = logging.getLogger(__name__)


def build_gmail_service(creds: Any) -> Any:
    try:
        from googleapiclient.discovery import build
    except ImportError as e:
        raise ImportError(
            "The 'google' optional dependencies are required to read Google emails"
        ) from e

    return build("gmail", "v1", credentials=creds)


def _search_latest_google(service: Any, query: str) -> dict | None:
    result: dict = service.users().messages().list(userId="me", q=query).execute()
    messages: list[dict] = list(result.get("messages", []))

    while "nextPageToken" in result:
        result = (
            service.users()
            .messages()
            .list(userId="me", q=query, pageToken=result["nextPageToken"])
            .execute()
        )
        messages.extend(result.get("messages", []))

    return messages[0] if messages else None


def _gmail_html(payload: dict) -> str | None:
    """Depth-first search of the MIME tree for the first text/html body."""
    data = (payload.get("body") or {}).get("data")

    if data and payload.get("mimeType") == "text/html":
        # Gmail strips base64 padding; restore it before decoding.
        padded = data + "=" * (-len(data) % 4)
        return urlsafe_b64decode(padded).decode("utf-8", errors="replace")

    for part in payload.get("parts") or []:
        html = _gmail_html(part)
        if html is not None:
            return html

    return None


def read_emails(creds: Any, tmp_path: Path) -> Path:
    try:
        from google.auth.exceptions import RefreshError
        from googleapiclient.errors import HttpError
    except ImportError as e:
        raise ImportError(
            "The 'google' optional dependencies are required to read Google emails"
        ) from e

    try:
        service = build_gmail_service(creds)

        latest = _search_latest_google(
            service,
            'from:noreply@leagueofcomicgeeks.com subject:"Your Comic Pull List for"',
        )
        if latest is None:
            logger.info("No emails were found with subject 'Your Comic Pull List for'")
            raise EmailError("No pull list emails were found") from None

        msg: dict = (
            service.users()
            .messages()
            .get(userId="me", id=latest["id"], format="full")
            .execute()
        )

        subject = ""
        for header in msg.get("payload", {}).get("headers", []):
            if header.get("name", "").lower() == "subject":
                subject = header.get("value", "")
                break

        html_body = _gmail_html(msg.get("payload", {}))
        if html_body is None:
            logger.warning("Email does not contain an HTML body")
            raise EmailError("Email does not contain an HTML body") from None

        return save_pull_list(tmp_path, subject, html_body)

    except RefreshError as re:
        logger.debug("Token expired/revoked %s", re, exc_info=True)
        raise AuthenticationError(
            "Token expired/revoked — delete token/token.pickle and re-authenticate."
        ) from None

    except HttpError as e:
        logger.debug("Gmail API error: %d %s", e.status_code, e.reason, exc_info=True)
        raise EmailError(f"Gmail API error: {e.status_code} {e.reason}") from None

    except httplib2.error.ServerNotFoundError:
        logger.debug("Gmail API server unreachable", exc_info=True)
        raise EmailError("Failed to connect to Gmail API services") from None

    except TimeoutError:
        logger.debug("Gmail API request timed out", exc_info=True)
        raise EmailError("Request to Gmail API timed out.") from None

    except gaierror:
        logger.debug("Gmail API DNS resolution failed", exc_info=True)
        raise EmailError("Could not resolve Gmail API server address.") from None
