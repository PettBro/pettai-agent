import logging
import os
from pathlib import Path


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
            logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
        )
        root_logger.addHandler(stream_handler)

    log_file_path = Path(__file__).resolve().parent / "log.txt"
    log_file_path.parent.mkdir(parents=True, exist_ok=True)

    if not any(
        isinstance(handler, logging.FileHandler)
        and getattr(handler, "baseFilename", None) == str(log_file_path)
        for handler in root_logger.handlers
    ):
        file_handler = logging.FileHandler(log_file_path)
        file_handler.setLevel(numeric_level)
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s %(name)s %(levelname)s: %(message)s")
        )
        root_logger.addHandler(file_handler)


_configure_logging()


__all__ = ["_configure_logging"]
