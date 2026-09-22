import logging
from datetime import UTC, datetime
from pathlib import Path

from komickers.exceptions import NoPullListError

logger = logging.getLogger(__name__)


def parse_pull_list_date(text: str | None) -> str | None:
    if not text:
        return None

    prefix = "Your Comic Pull List for "
    if not text.startswith(prefix):
        return None

    try:
        date = datetime.strptime(text.removeprefix(prefix), "%B %d, %Y").replace(
            tzinfo=UTC
        )
    except ValueError:
        return None

    return date.strftime("%Y-%m-%d")


def save_pull_list(tmp_path: Path, subject: str, html_body: str) -> Path:
    """Shared sink: the ONE place that touches the filesystem.

    Policy (identical for both backends):
      - Non pull-list subjects yield None ("not a pull list email").
      - If `<folder>/index.html` already exists, skip re-downloading.
      - Otherwise create the dated folder, write index.html, return it.
    """

    folder_name = parse_pull_list_date(subject)
    if folder_name is None:
        logger.warning("Not a pull list email: %s", subject)
        raise NoPullListError("Not a pull list")

    email_path = tmp_path / folder_name

    if (email_path / "index.html").exists():
        logger.info(
            "The latest pull list's index file already exists: %s", email_path.name
        )
        print("-------------------------****-------------------------")
        return email_path

    email_path.mkdir(parents=True, exist_ok=True)

    with open(email_path / "index.html", "w", encoding="utf-8") as f:
        f.write(html_body)

    logger.debug("Saved to %s", email_path)
    logger.info("Saved the pull list for %s", email_path.name)
    print("-------------------------****-------------------------")
    return email_path
