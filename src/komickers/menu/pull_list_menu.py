from pathlib import Path

from komickers.config import resolve_dir
from komickers.core.downloader import (
    Inventory,
    download_from_inventory,
    extract_comics_from_file,
)
from komickers.core.extractor import extract_names
from komickers.exceptions import (
    AuthenticationError,
    DownloaderError,
    EmailError,
)
from komickers.mail_reader.reader import read_emails


def pull_list_menu(config: dict) -> None:
    print("\n=================== PULL LIST MENU ===================\n")
    resolve_dir(config["directories"]["tmp_dir"])

    pull_list_path: Path | None = None
    pulled: bool = False
    while not pulled:
        try:
            print(
                "Please select your preferred method of logging in:\n1) Google API\n2) IMAP\nq) Quit\n"
            )
            selection: str = input("your selection: ")
            if selection == "q":
                print("Returning to the main menu...")
                print("\n======================================================\n")
                return

            pull_list_path = read_emails(config, selection)
            pulled = True

        except AuthenticationError as ae:
            print(f"\nAuthentication failed: {ae}")
            print("\n======================================================\n")
            return

        except EmailError as ee:
            print(f"Email error: {ee}")
            print("\n======================================================\n")
            return

        except ValueError:
            print(
                "\n.===============================."
                "\n||Please select a correct option||"
                "\n^===============================^\n"
            )

        except ImportError as ie:
            print(ie)
            selection = input("\nWould you like to download the dependencies? [N/y]")
            if selection in {"y", "yes"}:
                ...

    if pull_list_path is None:
        print("Couldn't determine the path of the pull list. Aborting...")
        print("\n======================================================\n")
        return

    index_path: Path = pull_list_path / "index.html"
    inbox_path: Path = resolve_dir(config["download"]["downloads_dir"])
    method: str = config["download"]["download_manager"]
    pull_list: list[tuple[str, str]] | None = extract_names(index_path)

    if pull_list is None:
        print("Couldn't extract comic names. Aborting...")
        print("\n======================================================\n")
        return

    inventory: Inventory | None = extract_comics_from_file(pull_list_path, pull_list)

    if inventory is None:
        print("An error occured while extracting download links...")
        print("\n======================================================\n")
        return

    try:
        download_from_inventory(inventory, inbox_path, method)
    except DownloaderError as de:
        print(de)
        print("\n======================================================\n")
