from __future__ import annotations

import logging
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from komickers.exceptions import AuthenticationError, EmailError, NoPullListError

# Ruff, mypy, and IDEs will treat this as a valid import.
# At runtime, TYPE_CHECKING is False, so nothing is imported.
if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials


logger = logging.getLogger(__name__)


def get_credentials(
    token_path: Path, credentials_path: Path, scopes: list[str]
) -> Credentials | None:
    try:
        from google.auth.exceptions import TransportError, RefreshError
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
        from google.oauth2.credentials import Credentials
    except ImportError as e:
        raise ImportError(
            "The 'google' optional dependencies is required to use OAuth2"
        ) from e

    creds: Credentials | None = None
    token_path.mkdir(parents=True, exist_ok=True)
    token_file: Path = token_path / "token.json"

    if token_file.exists():
        try:
            logger.info("Reading token file...")
            creds = Credentials.from_authorized_user_file(str(token_file), scopes)

        except (ValueError, json.JSONDecodeError) as e:
            logger.warning("Token file unreadable, re-authenticating: %s", e)
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            logger.info("Credentials outdated. Refreshing...")
            try:
                creds.refresh(Request())
            except TransportError as te:
                logger.debug(
                    "Failed to refresh OAuth2 credentials: %s", te, exc_info=True
                )
                raise EmailError("Failed to refresh OAuth2 credentials") from te

            except RefreshError as re:
                logger.debug("Refresh token revoked/expired: %s", re, exc_info=True)
                raise AuthenticationError(
                    "Token expired or revoked — delete the token file and sign in again."
                ) from re
        else:
            try:
                logger.info("Credentials not available. Creating them...")
                flow = InstalledAppFlow.from_client_secrets_file(
                    str(credentials_path / "credentials.json"),
                    scopes,
                )
                creds = flow.run_local_server(port=0)
            except FileNotFoundError as fnfe:
                logger.debug("Missing credentials file: %s", fnfe)
                raise AuthenticationError(
                    f"OAuth client not found at {credentials_path / 'credentials.json'}. "
                    "See README → Google API setup to create one."
                ) from fnfe

        with open(token_file, "w", encoding="utf-8") as token:
            token.write(creds.to_json())

    return creds


def parse_pull_list_date(text: str | None) -> str | None:
    if not text:
        return None

    prefix = "Your Comic Pull List for "
    if not text.startswith(prefix):
        return None

    try:
        date = datetime.strptime(text.removeprefix(prefix), "%B %d, %Y").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None

    return date.strftime("%Y-%m-%d")


def save_pull_list(tmp_path: Path, subject: str, html_body: str) -> Path:
    """Shared sink: the ONE place that touches the filesystem.

    Policy (identical for both backends):
      - Non pull-list subjects yield None ("not a pull list email").
      - If `<folder>/index.html` already exists, skip re-downloading.
      - Otherwise create the dated folder, write index.html, return it.
    """

    folder_name = parse_pull_list_date(subject)
    if folder_name is None:
        logger.warning("Not a pull list email: %s", subject)
        raise NoPullListError("Not a pull list")

    email_path = tmp_path / folder_name

    if (email_path / "index.html").exists():
        logger.info(
            "The latest pull list's index file already exists: %s", email_path.name
        )
        print("-------------------------****-------------------------")
        return email_path

    email_path.mkdir(parents=True, exist_ok=True)

    with open(email_path / "index.html", "w", encoding="utf-8") as f:
        f.write(html_body)

    logger.debug("Saved to %s", email_path)
    logger.info("Saved the pull list for %s", email_path.name)
    print("-------------------------****-------------------------")
    return email_path
