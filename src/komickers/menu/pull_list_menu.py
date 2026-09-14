from pathlib import Path

import httpx

from komickers.config import Config, resolve_dir
from komickers.core.downloader import (
    Inventory,
    download_from_inventory,
    extract_comics_from_file,
)
from komickers.core.extractor import (
    extract_names,
    extract_selection_from_pull_list,
    extract_selection_list_from_file,
    get_year,
)
from komickers.exceptions import (
    AuthenticationError,
    DownloaderError,
    EmailError,
    ExtractionError,
)
from komickers.mail_reader.reader import read_emails


def pull_list_menu(config: Config, client: httpx.Client) -> None:
    print("\n=================== PULL LIST MENU ===================\n")

    # Create the temporary directory
    resolve_dir(config.directories.tmp_dir)
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
    inbox_path: Path = resolve_dir(config.download.downloads_dir)
    method: str = config.download.download_manager

    try:
        pull_list: list[tuple[str, str]] = extract_names(index_path, inbox_path)

    except ExtractionError as ee:
        print(ee)
        print("\n======================================================\n")
        return

    print("The following comics were pulled:")
    for i, comic in enumerate(pull_list, start=1):
        print(f"{i})", comic[0])

    selection_input: str = input(
        "\nprovide the index of the comics to search for (0 for exit, all for all of them): "
    )

    selection_list: list[int]
    if selection_input == "0":
        print("No comics were selected. Aborting...")
        print("\n======================================================\n")
        return

    elif selection_input.lower() == "all":
        selection_list = [i for i in range(len(pull_list))]

    else:
        selection_list = [int(item.strip()) - 1 for item in selection_input.split(",")]

    selection_path: Path = extract_selection_from_pull_list(
        pull_list, selection_list, pull_list_path
    )

    selection_names: list[tuple[str, str]] = extract_selection_list_from_file(
        selection_path, get_year(pull_list_path.name)
    )

    try:
        inventory: Inventory = extract_comics_from_file(
            pull_list_path, selection_names, client
        )
        download_from_inventory(inventory, inbox_path, method)
    except DownloaderError as de:
        print(de)
        print("\n======================================================\n")
