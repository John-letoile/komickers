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
    hits: list[str]
    misses: list[str]
    hits_path: Path


def save_html_file(
    comic_name: str, comic_name_formatted: str, pull_list_path: Path
) -> Path:
    url: str = f"https://getcomics.org/marvel{comic_name_formatted}"
    tmp_html_dir: Path = pull_list_path / "comics_indexes"
    tmp_html_dir.mkdir(parents=True, exist_ok=True)

    file_path: Path = tmp_html_dir / f"{comic_name_formatted[1:-1]}.html"

    if file_path.exists():
        logger.info("the HTML file for '%s' already exists. Skipping...", comic_name)
        return file_path

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
    """Shell-free, platform-independent, strictly sequential wget2 download.
    Reads the URL file in Python and invokes wget2 once per URL.
    Nothing runs in parallel.
    """

    logger.info("Downloading...")

    list_of_urls: list[str] = [
        line.strip()
        for line in urls_file_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    for url in list_of_urls:
        logger.info("Downloading %s", url)
        try:
            subprocess.run(
                [
                    "wget2",
                    "--force-progress",
                    "--trust-server-names",
                    "-P",
                    str(inbox_dir),
                    url,
                ],
                check=True,
            )
        except FileNotFoundError as e:
            logger.debug("wget2 missing: %s", e, exc_info=True)
            raise DownloaderError("Download manager 'wget2' missing") from e
        except subprocess.CalledProcessError as e:
            logger.debug(
                "wget2 exited with code %d for %s", e.returncode, url, exc_info=True
            )
            raise DownloaderError(f"Download manager 'wget2' failed for {url}") from e


def download_comics_surgeDM(urls_file_path: Path, inbox_dir: Path) -> None:
    try:
        logger.info("Downloading...")
        subprocess.run(
            ["surge", "--batch", urls_file_path, "--output", inbox_dir],
            check=True,
        )
    except FileNotFoundError as fnfe:
        logger.debug("Missing the 'surge' download manager: %s", fnfe)
        raise DownloaderError("Missing the 'surge' download manager")


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
    tmp_path: Path, pull_list: list[tuple[str, str]]
) -> Inventory:
    misses: list[str] = []
    hits: list[str] = []

    hits_path = tmp_path / "hits.txt"
    missed_path = tmp_path / "misses.txt"

    # clean up files before writing to them
    hits_path.write_text("")
    missed_path.write_text("")

    with (
        hits_path.open("a", encoding="utf-8") as pulled_file,
        missed_path.open("a", encoding="utf-8") as missed_file,
    ):
        logger.info("Extracting download links...")
        print("\n-------------------------****-------------------------\n")

        for comic in pull_list:
            logger.info("Trying to find '%s'", comic[0])
            try:
                comic_html_file = save_html_file(comic[0], comic[1], tmp_path)
                logger.info("Found page. Extracting download link for '%s'", comic[0])
                extracted_comic_link = extract_download_link(comic_html_file, comic[0])
                logger.info("Successfully extracted download link for '%s'", comic[0])
                hits.append(comic[0])
                pulled_file.write(f"{extracted_comic_link}\n")
                print("\n-------------------------****-------------------------\n")

            except ExtractionError as ee:
                logger.warning(ee)
                _log_missed_comics(misses, missed_file, comic[0])

    return Inventory(hits, misses, hits_path)


def download_from_inventory(
    comics_inventory: Inventory, inbox_path: Path, method: str
) -> None:

    pulled_comics: list[str] = comics_inventory.hits
    missed_comics: list[str] = comics_inventory.misses
    extracted_urls_path: Path = comics_inventory.hits_path

    if len(pulled_comics) == 0:
        logger.info("No comics were pulled. Aborting...")
        print("\n======================================================\n")
        return

    print("The following comics were available:")
    for i, comic in enumerate(pulled_comics, start=1):
        print(f"{i})", comic)

    if missed_comics:
        print("\nThe following comics were unavailable:")
        for i, comic in enumerate(missed_comics, start=1):
            print(f"{i})", comic)

    print("\n-------------------------****-------------------------\n")
    download_permission = input("start downloading [N/y]? ")

    if download_permission.lower() in {"y", "yes", "yep"}:
        inbox_path.mkdir(parents=True, exist_ok=True)
        download_comics(extracted_urls_path, inbox_path, method)

    else:
        logger.info("Aborting...")
        print("\n======================================================\n")
        return

    logger.info("Successfully downloaded comics")
    print("\n======================================================\n")
