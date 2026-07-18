"""Engine logging configuration.

Provides a configurable logger hierarchy under `aeon.*` with both console
and file handlers, structured formatting, and per-module log levels.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional


_LOGGER_NAME = "aeon"
_configured = False


class _ColorFormatter(logging.Formatter):
    """ANSI colour formatter for the console handler."""

    _COLORS = {
        logging.DEBUG: "\033[37m",     # light grey
        logging.INFO: "\033[97m",      # bright white
        logging.WARNING: "\033[33m",   # yellow
        logging.ERROR: "\033[31m",     # red
        logging.CRITICAL: "\033[1;31m",  # bold red
    }
    _RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        color = self._COLORS.get(record.levelno, "")
        record.msg = f"{color}{record.msg}{self._RESET}" if color else record.msg
        return super().format(record)


def configure_logging(
    level: int = logging.INFO,
    log_file: Optional[Path] = None,
    file_level: int = logging.DEBUG,
    fmt: str = "%(asctime)s [%(levelname)-7s] %(name)s: %(message)s",
    datefmt: str = "%Y-%m-%d %H:%M:%S",
) -> None:
    """Configure the root `aeon` logger.

    Args:
        level: Console log level.
        log_file: Optional path to a rotating log file.
        file_level: Log level for the file handler.
        fmt: Logging format string.
        datefmt: Date format string.
    """
    global _configured
    root = logging.getLogger(_LOGGER_NAME)
    if _configured:
        for handler in list(root.handlers):
            root.removeHandler(handler)

    root.setLevel(min(level, file_level))
    formatter = logging.Formatter(fmt=fmt, datefmt=datefmt)

    console = logging.StreamHandler(stream=sys.stderr)
    console.setLevel(level)
    console.setFormatter(_ColorFormatter(fmt=fmt, datefmt=datefmt))
    root.addHandler(console)

    if log_file is not None:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        file_handler.setLevel(file_level)
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    root.propagate = False
    _configured = True


def get_logger(name: str = "engine") -> logging.Logger:
    """Return a child logger under the `aeon` hierarchy."""
    if not _configured:
        configure_logging()
    if name.startswith(_LOGGER_NAME):
        return logging.getLogger(name)
    return logging.getLogger(f"{_LOGGER_NAME}.{name}")
