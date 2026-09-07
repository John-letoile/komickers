"""Suggested fix for the broken wget2 download path.

Problem summary (see agent/CODEBASE_ANALYSIS.md §2.1):

    subprocess.run(["cat", path, "|", "xargs", ...], shell=True)

On POSIX, `shell=True` with a *list* does NOT join the list into a command
string. Only the first element is the shell command; the rest become shell
positional parameters ($0, $1, ...). So the above actually runs:

    /bin/sh -c 'cat'   # with the file path as $0, ignored

i.e. plain `cat` with no arguments and no stdin — it hangs forever reading
stdin and the wget2 pipeline never runs. Additionally:

  * `capture_output=True` swallowed all stdout/stderr (no visible progress,
    and `CalledProcessError` diagnostics were discarded).
  * `-q` suppressed wget2's own output, contradicting `--force-progress`.
  * An unquoted path in a shell string is a space-splitting bug and a
    command-injection risk.

This module contains the suggested replacement for
`src/komickers/core/downloader.py::download_comics_wget2`. Nothing else in
the codebase is modified by this file.

Two variants are provided:

  * `download_comics_wget2`      — POSIX pipeline + per-URL fallback on Windows.
  * `download_comics_wget2_noshell` — no `shell=True` anywhere: read the URL
    file in Python and invoke wget2 once per URL on every platform. This is
    the simplest and most portable option.

Variants provided:

  * `download_comics_wget2_queue` — RECOMMENDED. Configurable-worker queue:
    at most N wget2 downloads in flight via a ThreadPoolExecutor, per-URL
    error reporting, no shell anywhere. `workers=3` mirrors the original
    `xargs -n3 -P1` behavior (wget2 downloads its multiple URL arguments
    concurrently, so the original pipeline was effectively a 3-slot queue).

  * `download_comics_wget2`       — POSIX shell pipeline + sequential
    fallback on Windows (preserves the original `xargs -n3 -P1` shape).

  * `download_comics_wget2_noshell` — strictly sequential: one URL at a
    time, one wget2 process at a time.

To use: replace the existing function body in downloader.py with one of
these (and add the corresponding imports).
"""

from __future__ import annotations

import logging
import shlex
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from komickers.exceptions import DownloaderError

logger = logging.getLogger(__name__)

_WGET2_ARGS = [
    "wget2",
    # "-q",  # intentionally omitted: quiet mode hides all progress output
    "--force-progress",
    "--trust-server-names",
]


def _read_urls(urls_file_path: Path) -> list[str]:
    return [
        line.strip()
        for line in urls_file_path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _wget2_one(url: str, inbox_dir: Path) -> str:
    """Run a single wget2 download; return the URL or raise DownloaderError."""
    try:
        subprocess.run(
            [*_WGET2_ARGS, "-P", str(inbox_dir), url],
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
    return url


def download_comics_wget2_queue(
    urls_file_path: Path, inbox_dir: Path, workers: int = 3
) -> None:
    """Download all URLs with at most `workers` wget2 downloads in flight.

    A configurable replacement for the original `xargs -n3 -P1` pipeline:
    the same 3-at-a-time concurrency by default, but tunable, shell-free,
    and with per-URL error reporting that collects all failures instead of
    aborting the batch on the first one.
    """
    logger.info("Downloading with %d parallel worker(s)...", workers)

    urls = _read_urls(urls_file_path)
    if not urls:
        logger.info("No URLs to download. Aborting...")
        return

    failed: list[str] = []
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = {pool.submit(_wget2_one, url, inbox_dir): url for url in urls}
        for future in as_completed(futures):
            url = futures[future]
            try:
                future.result()
                logger.info("Finished %s", url)
            except DownloaderError as de:
                logger.warning("%s", de)
                failed.append(url)

    if failed:
        raise DownloaderError(
            f"wget2 failed for {len(failed)} comic(s): {', '.join(failed)}"
        )

    logger.info("Successfully downloaded comics")


# ---------------------------------------------------------------------------
# Variant 2: POSIX shell pipeline (matches the original intent)
# ---------------------------------------------------------------------------


def download_comics_wget2(urls_file_path: Path, inbox_dir: Path) -> None:
    """POSIX pipeline version of the original `xargs -n3 -P1` shape.

    Properly quoted *shell string* (not a broken argv list), no `-q`, no
    `capture_output` — progress is visible. Windows falls back to the
    strictly sequential per-URL variant (no /bin/sh pipeline there).
    """
    logger.info("Downloading...")

    if sys.platform == "win32":
        _wget2_sequential(urls_file_path, inbox_dir)
        return

    command = (
        f"cat {shlex.quote(str(urls_file_path))} | "
        f"xargs -n3 -P1 wget2 --force-progress --trust-server-names "
        f"-P {shlex.quote(str(inbox_dir))}"
    )

    try:
        subprocess.run(command, shell=True, check=True)
    except FileNotFoundError as e:
        logger.debug("wget2 missing: %s", e, exc_info=True)
        raise DownloaderError("Download manager 'wget2' missing") from e
    except subprocess.CalledProcessError as e:
        logger.debug("wget2 exited with code %d", e.returncode, exc_info=True)
        raise DownloaderError("Download manager 'wget2' failed") from e


# ---------------------------------------------------------------------------
# Variant 3: strictly sequential, no shell
# ---------------------------------------------------------------------------


def _wget2_sequential(urls_file_path: Path, inbox_dir: Path) -> None:
    for url in _read_urls(urls_file_path):
        logger.info("Downloading %s", url)
        _wget2_one(url, inbox_dir)


def download_comics_wget2_noshell(urls_file_path: Path, inbox_dir: Path) -> None:
    """Shell-free, platform-independent, strictly sequential wget2 download.

    Reads the URL file in Python and invokes wget2 once per URL. No
    `shell=True`, no pipeline, no quoting concerns, identical behavior on
    Linux, Windows, and macOS. Nothing runs in parallel.
    """
    logger.info("Downloading...")
    _wget2_sequential(urls_file_path, inbox_dir)


list = Path("/home/arshia/.cache/komickers/.tmp/2026-09-02/pulled_list.txd")
inbox = Path("/home/arshia/Downloads/Komickers/")
download_comics_wget2_queue(list, inbox, 3)
