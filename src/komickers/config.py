import logging
import os
import re
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path

import tomlkit
from platformdirs import PlatformDirs

from komickers.exceptions import ConfigError

logger = logging.getLogger(__name__)
_dirs = PlatformDirs(appname="komickers", appauthor=False)
EMAIL_REGEX = re.compile(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$")


def _get_default(section: str, subkey: str) -> str | list[str]:
    default_directories_config: DirectoriesConfig = DirectoriesConfig()
    default_download_config: DownloadConfig = DownloadConfig()
    default_email_config: EmailConfig = EmailConfig()

    if section == "directories":
        return default_directories_config.to_dict()[subkey]

    elif section == "download":
        return default_download_config.to_dict()[subkey]

    elif section == "email":
        return default_email_config.to_dict()[subkey]

    else:
        logger.debug(
            "Invalid default value call: [section]: %s, [subkey]: %s", section, subkey
        )
        raise ConfigError(f"Invalid config section/key value: [{section}] : [{subkey}]")


class DownloadManager(Enum):
    SURGE = "surge"
    UGET = "uget"
    WGET2 = "wget2"


@dataclass
class DirectoriesConfig:
    tmp_dir: str = str(Path(_dirs.user_cache_dir) / ".tmp")
    credentials_dir: str = str(_dirs.user_config_dir)
    token_dir: str = str(Path(_dirs.user_cache_dir) / "token")

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class DownloadConfig:
    downloads_dir: str = str(Path(_dirs.user_downloads_dir) / "Komickers")
    download_manager: str = "surge"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EmailConfig:
    scopes: list[str] = field(default_factory=lambda: ["https://mail.google.com/"])
    email_address: str = ""
    provider: str = "noreply@leagueofcomicgeeks.com"
    app_password: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Config:
    directories: DirectoriesConfig = field(default_factory=DirectoriesConfig)
    download: DownloadConfig = field(default_factory=DownloadConfig)
    email: EmailConfig = field(default_factory=EmailConfig)

    def to_dict(self) -> dict:
        return asdict(self)


def _config_path() -> Path:
    """Platform-correct location of the config file (Linux, Windows, macOS)."""
    return Path(_dirs.user_config_dir) / "komickers.toml"


def validate(config: Config) -> bool:
    try:
        DownloadManager(config.download.download_manager)
    except ValueError as ve:
        valid = [download_manager.value for download_manager in DownloadManager]
        logger.debug("Invalid download manager selection: %s", ve, exc_info=True)
        raise ConfigError(f"Invalid download manager. Must be one of: {valid}")

    if config.email.email_address and not EMAIL_REGEX.match(config.email.email_address):
        logger.debug("Invalid email format: %s", config.email.email_address)
        raise ConfigError(f"Invalid email format: {config.email.email_address}")

    paths: list[str] = [
        config.directories.credentials_dir,
        config.directories.tmp_dir,
        config.directories.token_dir,
        config.download.downloads_dir,
    ]

    for path in paths:
        if "\0" in path:
            logger.debug("Invalid path: {%s}", path)
            raise ConfigError(f"Invalid path: {path}")

    return True


def resolve_dir(value: str, *, create: bool = True) -> Path:
    """Turn a config string into an absolute, usable directory Path.

    - Expands '~' and environment variables ($VAR on POSIX, %VAR% on Windows)
    - Anchors relative paths to the app's platform data directory so the
      result never depends on the current working directory or install location
    - Creates the directory (and parents) unless create=False
    - Raises ConfigError early if the value is empty or cannot be created
    """
    if not value or not value.strip():
        raise ConfigError("Config directory value is empty")

    path = Path(os.path.expandvars(value)).expanduser()

    if not path.is_absolute():
        path = Path(_dirs.user_data_dir) / path

    if create:
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise ConfigError(f"Cannot create directory {path}: {e}") from e

    return path


def _from_dict(data: dict) -> Config:
    try:
        return Config(
            directories=DirectoriesConfig(**data.get("directories", {})),
            download=DownloadConfig(**data.get("download", {})),
            email=EmailConfig(**data.get("email", {})),
        )
    except TypeError as e:
        raise ConfigError(f"Invalid configuration: {e}") from e


def load_config() -> Config:
    path = _config_path()
    if not path.exists():
        return Config()

    with open(path, "r", encoding="utf-8") as f:
        data = tomlkit.load(f)

    try:
        validate(_from_dict(data))
    except ConfigError as ce:
        logger.debug("Invalid config: %s", ce)
        raise ConfigError(f"Invalid config: {ce}") from ce

    return _from_dict(data)


def save_config(config: Config) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        validate(config)
    except ConfigError as ce:
        logger.debug("Invalid config: %s", ce)
        raise ConfigError(f"Invalid config: {ce}")

    with open(path, "w", encoding="utf-8") as f:
        tomlkit.dump(config.to_dict(), f)

    path.chmod(0o600)


def update_config(**kwargs) -> None:
    config = load_config().to_dict()

    valid_keys = {
        "tmp_dir": ("directories", "tmp_dir"),
        "credentials_dir": ("directories", "credentials_dir"),
        "token_dir": ("directories", "token_dir"),
        "downloads_dir": ("download", "downloads_dir"),
        "download_manager": ("download", "download_manager"),
        "scopes": ("email", "scopes"),
        "email_address": ("email", "email_address"),
        "provider": ("email", "provider"),
        "app_password": ("email", "app_password"),
    }

    for key, value in kwargs.items():
        if key in valid_keys:
            section, subkey = valid_keys[key]
            if value == "!":
                pass

            elif str(value).strip() == "":
                config[section][subkey] = _get_default(section, subkey)

            else:
                config[section][subkey] = value

        else:
            logger.error("Invalid configuration: %s", key)
            raise ConfigError(f"Invalid configuration key: {key}")

    save_config(_from_dict(config))
