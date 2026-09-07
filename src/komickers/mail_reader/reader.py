from pathlib import Path

from komickers.config import resolve_dir

from .reader_google import read_emails as _read_emails_google
from .reader_imap import read_emails_app_password as _read_emails_app_password
from .reader_imap import read_emails_oauth as _read_emails_oauth
from .utils import get_credentials


def _fetch_method_for_imap() -> str:
    print(
        "\nPlease select one of the following ways to log into your account:\n1) App Password\n2) OAuth2"
    )
    return input("your selection: ")


def read_emails(config: dict, login_method: str) -> Path:
    tmp_path = resolve_dir(config["directories"]["tmp_dir"])

    if login_method == "1":
        token_path = resolve_dir(config["directories"]["token_dir"])
        credentials_path = resolve_dir(
            config["directories"]["credentials_dir"], create=False
        )
        scopes_google: list[str] = config["email"]["scopes"]
        creds = get_credentials(token_path, credentials_path, scopes_google)
        return _read_emails_google(creds, tmp_path)

    elif login_method == "2":
        email_address = config["email"]["email_address"]
        provider = config["email"]["provider"]
        auth_method = _fetch_method_for_imap()

        if auth_method == "1":
            app_password = config["email"]["app_password"]
            return _read_emails_app_password(
                email_address, app_password, provider, tmp_path
            )

        elif auth_method == "2":
            token_path = resolve_dir(config["directories"]["token_dir"])
            credentials_path = resolve_dir(
                config["directories"]["credentials_dir"], create=False
            )
            scopes_imap: list[str] = config["email"]["scopes"]
            creds = get_credentials(token_path, credentials_path, scopes_imap)
            return _read_emails_oauth(email_address, provider, tmp_path, creds)

        else:
            raise ValueError("Incorrect value picked")
    else:
        raise ValueError("Incorrect value picked")
