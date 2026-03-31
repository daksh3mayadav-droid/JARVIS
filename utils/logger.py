"""
utils/logger.py — Centralized logging for JARVIS

Provides rotating file + Rich console handlers.
Separate log files: jarvis.log, actions.log, errors.log
"""

from __future__ import annotations

import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Optional

try:
    from rich.logging import RichHandler
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

# ─── Constants ────────────────────────────────────────────────────────────────

LOG_DIR = Path("logs")
MAX_BYTES = 5 * 1024 * 1024   # 5 MB
BACKUP_COUNT = 5

_loggers: dict[str, logging.Logger] = {}
_setup_done = False


# ─── Setup ────────────────────────────────────────────────────────────────────

def setup_logging(log_level: str = "INFO") -> None:
    """
    Initialize the logging infrastructure.

    Creates the logs/ directory and attaches rotating-file handlers for:
      - logs/jarvis.log   (all levels)
      - logs/actions.log  (INFO+)
      - logs/errors.log   (ERROR+)

    A Rich console handler is added for terminal output.
    """
    global _setup_done
    if _setup_done:
        return

    LOG_DIR.mkdir(parents=True, exist_ok=True)

    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    root = logging.getLogger("jarvis")
    root.setLevel(numeric_level)
    root.propagate = False

    fmt = logging.Formatter(
        fmt="%(asctime)s [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ── Rotating file: everything ──
    _add_rotating_handler(root, LOG_DIR / "jarvis.log", logging.DEBUG, fmt)

    # ── Rotating file: actions (INFO+) ──
    _add_rotating_handler(root, LOG_DIR / "actions.log", logging.INFO, fmt)

    # ── Rotating file: errors only ──
    _add_rotating_handler(root, LOG_DIR / "errors.log", logging.ERROR, fmt)

    # ── Console handler ──
    if RICH_AVAILABLE:
        console_handler = RichHandler(
            level=numeric_level,
            rich_tracebacks=True,
            markup=True,
            show_time=True,
            show_path=False,
        )
    else:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(numeric_level)
        console_handler.setFormatter(fmt)

    root.addHandler(console_handler)
    _setup_done = True


def _add_rotating_handler(
    logger: logging.Logger,
    path: Path,
    level: int,
    fmt: logging.Formatter,
) -> None:
    """Attach a RotatingFileHandler to *logger*."""
    handler = RotatingFileHandler(
        str(path),
        maxBytes=MAX_BYTES,
        backupCount=BACKUP_COUNT,
        encoding="utf-8",
    )
    handler.setLevel(level)
    handler.setFormatter(fmt)
    logger.addHandler(handler)


# ─── Public API ───────────────────────────────────────────────────────────────

def get_logger(name: str, log_level: Optional[str] = None) -> logging.Logger:
    """
    Return a child logger under the 'jarvis' namespace.

    Args:
        name: Module/component name (e.g. "brain", "vision.ocr").
        log_level: Override log level for this specific logger (optional).

    Returns:
        Configured :class:`logging.Logger` instance.
    """
    if not _setup_done:
        setup_logging()

    full_name = f"jarvis.{name}"
    if full_name in _loggers:
        return _loggers[full_name]

    logger = logging.getLogger(full_name)
    if log_level:
        logger.setLevel(getattr(logging, log_level.upper(), logging.INFO))

    _loggers[full_name] = logger
    return logger
