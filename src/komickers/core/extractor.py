import logging
import re
from pathlib import Path

import httpx
from bs4 import BeautifulSoup

from komickers.exceptions import ExtractionError

logger = logging.getLogger(__name__)
SPECIAL_CHARACTERS: tuple[str, ...] = ("#", "(", ")", "!", "?", ":")


def get_year(file_path: Path) -> str:
    return file_path.parent.name[:4]


def formatter(year: str, line: str) -> str:
    if "\u2013" in line:
        line = line.replace("\u2013", "-")
    no_space_line: str = line.replace(" ", "-")
    translated_line = no_space_line.translate(
        str.maketrans("", "", "".join(SPECIAL_CHARACTERS))
    )
    translated_line = re.sub(r"-{2,}", "-", translated_line.lower())
    return f"/{translated_line.lower()}-{year}/"


def extract_names(file_path: Path) -> list[tuple[str, str]]:
    list_of_comics: list[tuple[str, str]] = []
    year: str = get_year(file_path)

    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # Find the heading that identifies the Pull List section.
    heading = soup.find(
        lambda tag: (
            tag.name in {"h1", "h2", "h3"}
            and "Your Pull List" in tag.get_text(" ", strip=True)
        )
    )

    if heading is None:
        logger.error("No 'Pull List' section")
        raise ExtractionError(
            f"Failed to find 'Pull List' section in {file_path}"
        ) from None

    section = heading.find_parent("table")

    if section is None:
        logger.error("No 'Pull List' container")
        raise ExtractionError(
            f"Failed to find 'Pull List' container in {file_path}"
        ) from None

    for link in section.find_all("a", href=True):
        href = link["href"]
        if "/comic/" not in href:
            continue

        title = link.get("title")

        if title:
            list_of_comics.append((str(title), formatter(year, str(title))))

    return list_of_comics


def extract_download_link(file_path: Path) -> str:
    with open(file_path, "r", encoding="utf-8") as f:
        soup = BeautifulSoup(f, "html.parser")

    # case sensitive. change if website changes format
    anchor = soup.select_one('a[title="DOWNLOAD NOW"]')

    if anchor is None:
        logger.warning("No 'DOWNLOAD NOW' link found in %s", file_path)
        raise ExtractionError(f"No download link found in {file_path.name}") from None

    download_url: str | None = anchor.get("href")  # type: ignore[assignment]

    if not download_url:
        logger.warning("Download anchor has no 'href' in %s", file_path)
        raise ExtractionError(f"Download link has no URL in {file_path.name}") from None

    server_side_url: str | None = None
    with httpx.Client() as client:
        response = client.head(download_url, follow_redirects=False, timeout=10)
        if response.status_code in (301, 302, 303, 307, 308):
            server_side_url = response.headers.get("location")
        else:
            logger.error(
                "Failed to extract download link for %s: %d",
                file_path,
                response.status_code,
            )
            raise ExtractionError(
                f"Failed to extract download link for {file_path.name}"
            ) from None

    if server_side_url is None:
        logger.warning("The server response missed a 'location' field")
        raise ExtractionError("The server response missed a 'location' field")

    return server_side_url
