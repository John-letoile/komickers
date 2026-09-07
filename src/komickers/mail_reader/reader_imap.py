import email
import imaplib
import logging
from email import policy
from email.message import EmailMessage
from pathlib import Path
from socket import gaierror
from typing import Any

from komickers.exceptions import AuthenticationError, EmailError, InboxError
from komickers.mail_reader.utils import save_pull_list

logger = logging.getLogger(__name__)
FetchedEmail = tuple[str, str]  # (subject, html_body)


def _extract_html(msg: EmailMessage) -> str | None:
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/html":
                return str(part.get_content())
    elif msg.get_content_type() == "text/html":
        return str(msg.get_content())
    return None


def _fetch_latest_imap(mail: imaplib.IMAP4_SSL, provider: str) -> FetchedEmail | None:
    status, data = mail.search(
        None, f'(FROM "{provider}" SUBJECT "Your Comic Pull List for")'
    )
    if status != "OK" or not data[0]:
        return None

    # Message IDs come back in ascending order; the last one is newest.
    message_id = data[0].split()[-1]

    status, data = mail.fetch(message_id, "(RFC822)")
    if status != "OK":
        raise imaplib.IMAP4.error("Failed to fetch email")

    if data is None or not data[0]:
        raise imaplib.IMAP4.error("Failed to fetch email")

    msg = email.message_from_bytes(data[0][1], policy=policy.default)  # type: ignore[arg-type]
    subject = str(msg["Subject"] or "")

    html_body = _extract_html(msg)
    if html_body is None:
        return None

    return subject, html_body


def read_emails_app_password(
    email_address: str, app_password: str, provider: str, tmp_path: Path
) -> Path | None:
    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", timeout=10) as mail:
            try:
                mail.login(email_address, app_password)
            except imaplib.IMAP4.error as e:
                logger.debug(
                    "IMAP authentication failed for %s: %s",
                    email_address,
                    e,
                    exc_info=True,
                )
                raise AuthenticationError(f"IMAP authentication failed: {e}") from None

            try:
                mail.select("INBOX")
            except imaplib.IMAP4.error as e:
                logger.debug("Failed to open INBOX: %s", e, exc_info=True)
                raise InboxError(f"Failed to open inbox: {e}") from None

            fetched = _fetch_latest_imap(mail, provider)

    except imaplib.IMAP4.error as e:
        logger.debug("IMAP connection failed: %s", e, exc_info=True)
        raise EmailError(f"IMAP connection failed: {e}") from None

    except TimeoutError:
        logger.debug("IMAP connection timed out", exc_info=True)
        raise EmailError("Connection to email server timed out.") from None

    except gaierror:
        logger.debug("IMAP DNS resolution failed", exc_info=True)
        raise EmailError("Could not resolve email server address.") from None

    if fetched is None:
        logger.warning("No matching pull list emails found via IMAP")
        raise EmailError("No pull list emails found in inbox.")

    return save_pull_list(tmp_path, *fetched)


def read_emails_oauth(
    email_address: str, provider: str, tmp_path: Path, creds: Any
) -> Path:
    auth_string = f"user={email_address}\x01auth=Bearer {creds.token}\x01"
    first_call = True

    def xoauth2(_challenge: bytes) -> bytes:
        nonlocal first_call
        if first_call:
            first_call = False
            return auth_string.encode()
        return b""

    try:
        with imaplib.IMAP4_SSL("imap.gmail.com", timeout=10) as mail:
            try:
                mail.authenticate("XOAUTH2", xoauth2)
            except imaplib.IMAP4.error as e:
                logger.debug(
                    "IMAP authentication failed for %s: %s",
                    email_address,
                    e,
                    exc_info=True,
                )
                raise AuthenticationError(f"IMAP authentication failed: {e}") from None

            try:
                mail.select("INBOX")
            except imaplib.IMAP4.error as e:
                logger.debug("IMAP failed to read inbox: %s", e, exc_info=True)
                raise InboxError(f"Failed to open inbox: {e}") from None

            # Search for messages from the sender whose subject contains the phrase
            fetched = _fetch_latest_imap(mail, provider)

    except imaplib.IMAP4.error as e:
        logger.debug("IMAP connection failed: %s", e, exc_info=True)
        raise EmailError(f"IMAP connection failed: {e}") from None

    except TimeoutError:
        logger.debug("IMAP connection timed out", exc_info=True)
        raise EmailError("Connection to email server timed out.") from None

    except gaierror:
        logger.debug("IMAP DNS resolution failed", exc_info=True)
        raise EmailError("Could not resolve email server address.") from None

    if fetched is None:
        logger.warning("No matching pull list emails found via IMAP OAuth")
        raise EmailError("No pull list emails found in inbox.")

    return save_pull_list(tmp_path, *fetched)
