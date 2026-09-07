import copy
import logging
import os
from pathlib import Path

import tomlkit
from platformdirs import PlatformDirs

from komickers.exceptions import ConfigError

logger = logging.getLogger(__name__)

_dirs = PlatformDirs(appname="komickers", appauthor=False)


def _config_path() -> Path:
    """Platform-correct location of the config file (Linux, Windows, macOS)."""
    return Path(_dirs.user_config_dir) / "komickers.toml"


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


def _default_config() -> dict:
    dirs = PlatformDirs(appname="komickers", appauthor=False)
    return {
        "directories": {
            "tmp_dir": str(Path(dirs.user_cache_dir) / ".tmp"),
            "credentials_dir": str(Path(dirs.user_config_dir)),
            "token_dir": str(Path(dirs.user_cache_dir) / "token"),
        },
        "download": {
            "downloads_dir": str(Path(dirs.user_downloads_dir) / "Komickers"),
            "download_manager": "surge",
        },
        "email": {
            "scopes": ["https://mail.google.com/"],
            "email_address": "",
            "provider": "noreply@leagueofcomicgeeks.com",
            "app_password": "",
        },
    }


def _deep_merge(base: dict, override: dict) -> dict:
    result = copy.deepcopy(base)
    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = _deep_merge(result[key], value)
        else:
            result[key] = value
    return result


def load_config() -> dict:
    path = _config_path()
    if not path.exists():
        return _default_config()

    with open(path, "r", encoding="utf-8") as f:
        data = tomlkit.load(f)

    if not _validate_config(data):
        logger.error("Invalid configuration")
        raise ConfigError("Invalid configuration")

    return _deep_merge(_default_config(), data)


# TODO: implement a config valdiator (via a schema)
def _validate_config(config: dict) -> bool:
    return True


def save_config(config: dict) -> None:
    path = _config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        tomlkit.dump(config, f)


def update_config(**kwargs) -> None:
    config = load_config()
    default_config = _default_config()

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
            config[section][subkey] = (
                default_config[section][subkey] if value == "" else value
            )
        else:
            logger.error("Invalid configuration: %s", key)
            raise ConfigError(f"Invalid configuration key: {key}")

    save_config(config)
