import logging
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO
import httpx

from komickers.exceptions import DownloaderError, ExtractionError

from .extractor import extract_download_link

logger = logging.getLogger(__name__)


@dataclass
class Inventory:
    pulled: list[str]
    missed: list[str]
    urls_path: Path


def save_html_file(
    comic_name: str, comic_name_formatted: str, pull_list_path: Path
) -> Path:
    url: str = f"https://getcomics.org/marvel{comic_name_formatted}"
    tmp_html_dir: Path = pull_list_path / "comics_indexes"
    tmp_html_dir.mkdir(parents=True, exist_ok=True)

    file_path: Path = tmp_html_dir / f"{comic_name_formatted[1:-1]}.html"

    with httpx.Client() as client:
        try:
            response: httpx.Response = client.get(
                url, follow_redirects=True, timeout=10
            )
            response.raise_for_status()

        except httpx.HTTPError as httpe:
            logger.debug(
                "Failed to fetch html file for %s: %s", comic_name, httpe, exc_info=True
            )
            raise ExtractionError(
                f"Failed to fetch html file for {comic_name}"
            ) from httpe

    output = response.content
    file_path.write_bytes(output)
    logger.info("Successfully saved '%s'", comic_name)
    return file_path


def download_comics_uget(urls_file_path: Path, inbox_dir: Path) -> None:
    logger.info("Downloading...")
    if sys.platform == "linux":
        subprocess.run(
            [
                "uget-gtk",
                "--quiet",
                f"--input-file={urls_file_path}",
                f"--folder={inbox_dir}",
            ],
            check=True,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )

    elif sys.platform == "win32":
        subprocess.run(
            [
                "uget",
                "--quiet",
                f"--input-file={urls_file_path}",
                f"--folder={inbox_dir}",
            ],
            check=True,
            stderr=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
        )

    else:
        raise RuntimeError(f"uGet is not supported for this platform: {sys.platform}")


def download_comics_wget2(urls_file_path: Path, inbox_dir: Path) -> None:
    logger.info("Downloading...")
    subprocess.run(
        [
            f"cat{urls_file_path}",
            "|",
            "xargs",
            "-n3",
            "-P1",
            "wget2",
            "-q",
            "--force-progress",
            "--trust-server-names",
            "-P",
            inbox_dir,
        ],
        check=True,
    )


def download_comics_surgeDM(urls_file_path: Path, inbox_dir: Path) -> None:
    logger.info("Downloading...")
    subprocess.run(
        ["surge", "--batch", urls_file_path, "--output", inbox_dir],
        check=True,
    )


def download_comics(urls_file_path: Path, inbox_dir: Path, method: str) -> None:
    try:
        if method.lower() == "uget":
            download_comics_uget(urls_file_path, inbox_dir)
        elif method.lower() == "wget2":
            download_comics_wget2(urls_file_path, inbox_dir)
        elif method.lower() == "surge":
            download_comics_surgeDM(urls_file_path, inbox_dir)
        else:
            raise DownloaderError("Please select one of the available download methods")

    except subprocess.CalledProcessError as e:
        logger.debug(
            "Download manager '%s' failed (exit code %d)",
            method,
            e.returncode,
            exc_info=True,
        )
        raise DownloaderError(f"Download manager '{method}' failed") from e

    except RuntimeError as rte:
        logger.debug("Download manager '%s' missing", method, exc_info=True)
        raise DownloaderError(f"Downloading manager '{method}' missing") from rte


def _log_missed_comics(missed_comics: list[str], missed_file: TextIO, comic: str):
    missed_comics.append(comic)
    missed_file.write(f"{comic}\n")
    print("\n-------------------------****-------------------------\n")


def extract_comics_from_file(
    pull_list_path: Path, pull_list: list[tuple[str, str]]
) -> Inventory:
    missed_comics: list[str] = []
    pulled_comics: list[str] = []

    extracted_urls_path = pull_list_path / "pulled_list.txt"
    missed_path = pull_list_path / "missed_list.txt"

    # clean up files before writing to them
    extracted_urls_path.write_text("")
    missed_path.write_text("")

    with (
        extracted_urls_path.open("a", encoding="utf-8") as pulled_file,
        missed_path.open("a", encoding="utf-8") as missed_file,
    ):
        logger.info("Extracting download links...")
        print("\n-------------------------****-------------------------\n")

        for comic in pull_list:
            logger.info("Trying to find '%s'", comic[0])
            try:
                comic_html_file = save_html_file(comic[0], comic[1], pull_list_path)

                # if comic_html_file is None:
                #     logger.warning("Couldn't find page for '%s'", comic[0])
                #     _log_missed_comics(missed_comics, missed_file, comic[0])
                #     continue

                logger.info("Found page. Extracting download link for '%s'", comic[0])

                extracted_comic_link = extract_download_link(comic_html_file)

                # if extracted_comic_link is None:
                #     logger.warning("Couldn't extract download link for '%s'", comic[0])
                #     _log_missed_comics(missed_comics, missed_file, comic[0])
                #     continue

                logger.info("Successfully extracted download link for '%s'", comic[0])
                pulled_comics.append(comic[0])
                pulled_file.write(f"{extracted_comic_link}\n")
                print("\n-------------------------****-------------------------\n")

            except FileNotFoundError:
                logger.info("Couldn't find the file")
                _log_missed_comics(missed_comics, missed_file, comic[0])

            except ExtractionError as ee:
                logger.warning(ee)
                _log_missed_comics(missed_comics, missed_file, comic[0])

    return Inventory(pulled_comics, missed_comics, extracted_urls_path)


def download_from_inventory(
    comics_inventory: Inventory, inbox_path: Path, method: str
) -> None:

    pulled_comics: list[str] = comics_inventory.pulled
    missed_comics: list[str] = comics_inventory.missed
    extracted_urls_path: Path = comics_inventory.urls_path

    if len(pulled_comics) == 0:
        logger.info("No comics were pulled. Aborting...")
        print("\n======================================================\n")
        return

    print("The following comics were pulled:")
    for i, comic in enumerate(pulled_comics, start=1):
        print(f"{i})", comic)

    if missed_comics:
        print("\nThe following comics were unavailable:")
        for i, comic in enumerate(missed_comics, start=1):
            print(f"{i})", comic)

    print("\n-------------------------****-------------------------\n")
    download_permission = input("would you like to download these comics [N/y]? ")
    if download_permission.lower() in {"y", "yes"}:
        inbox_path.mkdir(parents=True, exist_ok=True)
        download_comics(extracted_urls_path, inbox_path, method)

    else:
        logger.info("Aborting...")
        print("\n======================================================\n")
        return

    logger.info("Successfully downloaded comics")
    print("\n======================================================\n")
