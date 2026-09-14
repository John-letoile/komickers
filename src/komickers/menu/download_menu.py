from pathlib import Path

import httpx

from komickers.config import Config, resolve_dir
from komickers.core.downloader import (
    Inventory,
    download_from_inventory,
    extract_comics_from_file,
)
from komickers.core.extractor import formatter
from komickers.exceptions import DownloaderError


def download_menu(config: Config, client: httpx.Client) -> None:
    print("\n==================== DOWNLOAD MENU ===================\n")
    print(
        "Please provide a text file containing the download links of the comics to be downloaded."
    )
    pull_list_path: Path = Path(input("\nthe path to the text file: "))
    if not pull_list_path.is_file():
        print("The provided path doesn't exist. Aborting...")
        print("\n======================================================\n")
        return

    year: str = input("the year for this pull list: ")
    index_dir: Path = Path(input("the directory to save the index files to: "))

    try:
        index_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        print(
            "The provided directory for temporary files is not a directory. Aborting..."
        )
        print("\n======================================================\n")
        return

    with open(pull_list_path, "r", encoding="utf-8") as f:
        names: list[str] = [line.rstrip() for line in f if line.strip()]

    pull_list: list[tuple[str, str]] = [(name, formatter(year, name)) for name in names]
    inbox_path = resolve_dir(config.download.downloads_dir)
    method = config.download.download_manager
    inventory: Inventory = extract_comics_from_file(index_dir, pull_list, client)

    try:
        download_from_inventory(inventory, inbox_path, method)
    except DownloaderError as de:
        print(de)
        print("\n======================================================\n")
