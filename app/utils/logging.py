"""Logging configuration for local pipeline runs."""

import logging
from pathlib import Path


LOG_FORMAT = (
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)


def setup_logging(
    log_level: str = "INFO",
    log_file: str | Path | None = None,
) -> None:
    """Configure console logging and optional file logging."""

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
    ]

    if log_file is not None:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        handlers.append(
            logging.FileHandler(
                log_path,
                encoding="utf-8",
            )
        )

    logging.basicConfig(
        level=numeric_level,
        format=LOG_FORMAT,
        handlers=handlers,
        force=True,
    )

    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """Return a named logger."""

    return logging.getLogger(name)
