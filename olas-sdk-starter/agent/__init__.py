import logging
import os
import re
from pathlib import Path


_EMOJI_RE = re.compile(
    "["
    "\U0001f300-\U0001f9ff"  # Misc Symbols, Emoticons, etc.
    "\U00002702-\U000027b0"  # Dingbats
    "\U0000fe00-\U0000fe0f"  # Variation Selectors
    "\U0000200d"             # Zero Width Joiner
    "\U000020e3"             # Combining Enclosing Keycap
    "]+",
    flags=re.UNICODE,
)


class _AsciiFormatter(logging.Formatter):
    """Formatter that strips emoji from log messages for safe console output."""

    def format(self, record: logging.LogRecord) -> str:
        result = super().format(record)
        return _EMOJI_RE.sub("", result).strip()


def _configure_logging() -> None:
    log_level_env = os.environ.get("LOG_LEVEL", "INFO")
    try:
        numeric_level = int(str(log_level_env).strip())
    except ValueError:
        numeric_level = getattr(
            logging, str(log_level_env).strip().upper(), logging.INFO
        )

    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)

    if not root_logger.handlers:
        stream_handler = logging.StreamHandler()
        stream_handler.setLevel(numeric_level)
        stream_handler.setFormatter(
            _AsciiFormatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
        )
        root_logger.addHandler(stream_handler)

    log_file_path = Path(__file__).resolve().parent / "log.txt"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    if not any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == str(log_file_path)
        for handler in root_logger.handlers
    ):
        file_handler = logging.FileHandler(log_file_path, encoding="utf-8")
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
        )
        root_logger.addHandler(file_handler)


_configure_logging()


__all__ = ["_configure_logging", "_AsciiFormatter"]
