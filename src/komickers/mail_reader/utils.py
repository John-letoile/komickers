from __future__ import annotations

import logging
import pickle
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from komickers.exceptions import EmailError, NoPullListError

# Ruff, mypy, and IDEs will treat this as a valid import.
# At runtime, TYPE_CHECKING is False, so nothing is imported.
if TYPE_CHECKING:
    import google.oauth2.credentials.Credentials


logger = logging.getLogger(__name__)


def get_credentials(
    token_path: Path, credentials_path: Path, scopes: list[str]
) -> google.oauth2.credentials.Credentials:
    try:
        from google.auth.exceptions import TransportError
        from google.auth.transport.requests import Request
        from google_auth_oauthlib.flow import InstalledAppFlow
    except ImportError as e:
        raise ImportError(
            "The 'google' optional dependencies is required to use OAuth2"
        ) from e

    creds: google.oauth2.credentials.Credentials | None = None
    token_path.mkdir(parents=True, exist_ok=True)
    if (token_path / "token.pickle").exists():
        logger.info("Reading token file...")
        with open(str(token_path / "token.pickle"), "rb") as token:
            creds = pickle.load(token)

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
        else:
            logger.info("Credentials not available. Creating them...")
            flow = InstalledAppFlow.from_client_secrets_file(
                str(credentials_path / "credentials.json"),
                scopes,
            )
            creds = flow.run_local_server(port=0)

        with open(str(token_path / "token.pickle"), "wb") as token:
            pickle.dump(creds, token)

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
