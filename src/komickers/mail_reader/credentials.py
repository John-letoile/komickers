from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from komickers.exceptions import AuthenticationError, EmailError

if TYPE_CHECKING:
    from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)


def get_credentials(
    token_path: Path, credentials_path: Path, scopes: list[str]
) -> Credentials:
    try:
        from google.auth.exceptions import RefreshError, TransportError
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_oauthlib.flow import InstalledAppFlow
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
            token_file.chmod(0o0600)

    return creds


def verify_credentials(creds: Credentials, expected_email: str) -> bool:
    """Fetches the email address associated with a Gmail-scoped token."""
    try:
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as e:
        raise ImportError(
            "The 'google' optional dependencies is required to use OAuth2"
        ) from e

    try:
        service = build("gmail", "v1", credentials=creds)
        profile = service.users().getProfile(userId="me").execute()
        token_email = profile.get("emailAddress")

        if not token_email:
            raise EmailError("Gmail profile did not include an email address")

        return token_email.strip().lower() == expected_email.strip().lower()

    except HttpError as httpe:
        logger.debug("Failed to fetch Gmail profile: %s", httpe, exc_info=True)
        raise EmailError("Failed to fetch Gmail profile")


def get_app_password(email_address: str) -> str:
    """Return the Gmail app password: from the system keyring if available,
    otherwise prompt per-session (nothing is persisted)."""
    try:
        import keyring
    except ImportError:
        logger.debug("keyring not installed — falling back to per-session prompt")
        keyring = None

    if keyring is not None:
        try:
            stored = keyring.get_password("komickers", email_address)
            if stored:
                return stored
        except keyring.errors.NoKeyringError:
            logger.warning("No system keyring available — falling back to prompt")

    import getpass

    return getpass.getpass(f"Gmail app password for {email_address}: ")


def set_app_password(email_address: str):
    app_password: str = get_app_password(email_address)

    if app_password and app_password != "!":
        try:
            import keyring

            keyring.set_password("komickers", email_address, app_password)
        except ImportError:
            print("keyring not installed — the app password will NOT be saved.")
            print("Install it with: uv sync --extra imap  (then re-enter it once)")
