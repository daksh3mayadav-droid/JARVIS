"""
utils/helpers.py — Common utilities for JARVIS

Provides config loading, string formatting, path utilities,
retry decorator, fuzzy matching, and platform helpers.
"""

from __future__ import annotations

import functools
import json
import os
import platform
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

import yaml

# ─── Type Vars ────────────────────────────────────────────────────────────────

F = TypeVar("F", bound=Callable[..., Any])

# ─── Config ───────────────────────────────────────────────────────────────────

_config_cache: Optional[dict] = None
CONFIG_PATH = Path(__file__).parent.parent / "config.yaml"


def get_config() -> dict:
    """
    Load and cache the JARVIS config from config.yaml.

    Returns:
        Parsed YAML config as a nested dict.
    """
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            _config_cache = yaml.safe_load(f) or {}
    else:
        _config_cache = {}

    return _config_cache


def reload_config() -> dict:
    """Force reload config from disk."""
    global _config_cache
    _config_cache = None
    return get_config()


# ─── Formatting ───────────────────────────────────────────────────────────────

def format_file_size(num_bytes: int) -> str:
    """
    Convert byte count to human-readable string.

    Args:
        num_bytes: Raw byte count.

    Returns:
        String like "1.23 MB" or "456 KB".
    """
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(num_bytes) < 1024.0:
            return f"{num_bytes:.1f} {unit}"
        num_bytes /= 1024.0  # type: ignore[assignment]
    return f"{num_bytes:.1f} PB"


def format_timestamp(ts: Optional[float] = None) -> str:
    """
    Format a Unix timestamp as a human-readable string.

    Args:
        ts: Unix timestamp. Defaults to current time.

    Returns:
        Formatted string: "2025-01-15 14:30:00".
    """
    import datetime

    if ts is None:
        ts = time.time()
    return datetime.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")


def format_uptime(seconds: float) -> str:
    """Convert seconds to 'Xh Ym Zs' string."""
    hours, remainder = divmod(int(seconds), 3600)
    minutes, secs = divmod(remainder, 60)
    parts = []
    if hours:
        parts.append(f"{hours}h")
    if minutes:
        parts.append(f"{minutes}m")
    parts.append(f"{secs}s")
    return " ".join(parts)


# ─── Path Utilities ───────────────────────────────────────────────────────────

def get_common_paths() -> dict[str, Path]:
    """
    Return a dict of common Windows user paths.

    Returns:
        Dict with keys: desktop, downloads, documents, music, pictures,
        videos, appdata, temp.
    """
    home = Path.home()
    paths: dict[str, Path] = {
        "home": home,
        "desktop": home / "Desktop",
        "downloads": home / "Downloads",
        "documents": home / "Documents",
        "music": home / "Music",
        "pictures": home / "Pictures",
        "videos": home / "Videos",
        "appdata": Path(os.environ.get("APPDATA", home / "AppData" / "Roaming")),
        "localappdata": Path(os.environ.get("LOCALAPPDATA", home / "AppData" / "Local")),
        "temp": Path(os.environ.get("TEMP", home / "AppData" / "Local" / "Temp")),
        "program_files": Path(os.environ.get("PROGRAMFILES", "C:/Program Files")),
        "program_files_x86": Path(os.environ.get("PROGRAMFILES(X86)", "C:/Program Files (x86)")),
        "system_root": Path(os.environ.get("SYSTEMROOT", "C:/Windows")),
    }
    return paths


def ensure_dir(path: Path) -> Path:
    """Create directory (and parents) if it doesn't exist. Returns path."""
    path.mkdir(parents=True, exist_ok=True)
    return path


# ─── Platform ─────────────────────────────────────────────────────────────────

def is_windows() -> bool:
    """Return True if running on Windows."""
    return platform.system() == "Windows"


def is_linux() -> bool:
    """Return True if running on Linux."""
    return platform.system() == "Linux"


def is_mac() -> bool:
    """Return True if running on macOS."""
    return platform.system() == "Darwin"


# ─── Retry Decorator ──────────────────────────────────────────────────────────

def retry(
    attempts: int = 3,
    delay: float = 1.0,
    exceptions: tuple = (Exception,),
) -> Callable[[F], F]:
    """
    Decorator that retries a function on specified exceptions.

    Args:
        attempts: Max number of attempts.
        delay: Seconds to wait between retries.
        exceptions: Exception types to catch.

    Returns:
        Wrapped function.
    """
    def decorator(func: F) -> F:
        @functools.wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            last_exc: Optional[Exception] = None
            for attempt in range(1, attempts + 1):
                try:
                    return func(*args, **kwargs)
                except exceptions as exc:  # type: ignore[misc]
                    last_exc = exc
                    if attempt < attempts:
                        time.sleep(delay)
            raise last_exc  # type: ignore[misc]
        return wrapper  # type: ignore[return-value]
    return decorator


# ─── String Utilities ─────────────────────────────────────────────────────────

def fuzzy_match(query: str, candidates: list[str], threshold: float = 0.6) -> list[str]:
    """
    Return candidates that fuzzy-match query above the given threshold.

    Falls back to simple substring search if thefuzz is unavailable.

    Args:
        query: Search string.
        candidates: List of strings to match against.
        threshold: Similarity threshold (0–1). Default 0.6.

    Returns:
        Sorted list of matching candidates (best match first).
    """
    query_lower = query.lower()
    try:
        from thefuzz import process as fuzz_process
        results = fuzz_process.extract(query, candidates, limit=10)
        return [r[0] for r in results if r[1] / 100 >= threshold]
    except ImportError:
        pass

    # Simple fallback
    matches = []
    for c in candidates:
        c_lower = c.lower()
        if query_lower in c_lower or c_lower in query_lower:
            matches.append(c)
        elif _simple_similarity(query_lower, c_lower) >= threshold:
            matches.append(c)
    return matches


def _simple_similarity(a: str, b: str) -> float:
    """Compute a simple character-overlap similarity ratio."""
    if not a or not b:
        return 0.0
    common = sum(1 for ch in set(a) if ch in b)
    return common / max(len(set(a)), len(set(b)))


def truncate(text: str, max_len: int = 100, suffix: str = "...") -> str:
    """Truncate text to max_len characters."""
    if len(text) <= max_len:
        return text
    return text[: max_len - len(suffix)] + suffix


# ─── JSON ─────────────────────────────────────────────────────────────────────

def safe_json_parse(text: str, default: Any = None) -> Any:
    """
    Parse JSON safely, returning *default* on failure.

    Also handles JSON embedded in larger text by finding the first
    balanced '{...}' or '[...]' block.

    Args:
        text: String that may contain JSON.
        default: Value to return on parse failure.

    Returns:
        Parsed JSON object or *default*.
    """
    text = text.strip()
    # Direct parse
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # Try to extract embedded JSON object
    for start_char, end_char in [('{', '}'), ('[', ']')]:
        start = text.find(start_char)
        if start == -1:
            continue
        depth = 0
        for i, ch in enumerate(text[start:], start):
            if ch == start_char:
                depth += 1
            elif ch == end_char:
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except (json.JSONDecodeError, ValueError):
                        break

    return default


# ─── Async helpers ────────────────────────────────────────────────────────────

def run_in_thread(func: Callable, *args: Any, daemon: bool = True, **kwargs: Any):
    """
    Run *func* in a background daemon thread. Returns the Thread object.

    Args:
        func: Callable to run.
        *args: Positional arguments.
        daemon: Whether to set the thread as daemon. Default True.
        **kwargs: Keyword arguments.

    Returns:
        Running :class:`threading.Thread`.
    """
    import threading

    t = threading.Thread(target=func, args=args, kwargs=kwargs, daemon=daemon)
    t.start()
    return t
