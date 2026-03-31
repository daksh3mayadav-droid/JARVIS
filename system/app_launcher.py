"""
system/app_launcher.py — Installed app scanner and launcher for JARVIS

Scans Start Menu, Program Files, and Desktop shortcuts.
Fuzzy-matches app names and tracks launch history.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Optional

from utils.helpers import get_config, fuzzy_match
from utils.logger import get_logger

log = get_logger("system.app_launcher")

# ─── Built-in shortcuts ───────────────────────────────────────────────────────

BUILTIN_APPS: dict[str, str] = {
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "paint": "mspaint.exe",
    "wordpad": "wordpad.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "task manager": "taskmgr.exe",
    "file explorer": "explorer.exe",
    "control panel": "control.exe",
    "settings": "ms-settings:",
    "registry editor": "regedit.exe",
    "device manager": "devmgmt.msc",
    "disk management": "diskmgmt.msc",
    "event viewer": "eventvwr.msc",
    "snipping tool": "snippingtool.exe",
    "magnifier": "magnify.exe",
    "on-screen keyboard": "osk.exe",
    "clock": "ms-clock:",
    "calendar": "outlookcal:",
    "photos": "ms-photos:",
    "camera": "microsoft.windows.camera:",
    "store": "ms-windows-store:",
    "xbox": "ms-xbox-tcui:",
}

# Directories to scan for .exe and .lnk files
SCAN_DIRS = [
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\Windows",
    r"C:\Windows\System32",
]

SHORTCUT_DIRS = [
    Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu",
    Path("C:/ProgramData/Microsoft/Windows/Start Menu"),
    Path.home() / "Desktop",
    Path("C:/Users/Public/Desktop"),
]


class AppLauncher:
    """
    Installed application scanner and launcher.

    Builds a searchable app database on first use.
    Uses fuzzy matching to find apps by partial name.
    Tracks recently and frequently used apps via Memory.
    """

    def __init__(self) -> None:
        """Initialize the app launcher."""
        self._app_db: dict[str, str] = {}  # name_lower → path
        self._db_built = False
        self._memory = None  # Injected later if needed
        log.info("AppLauncher initialized.")

    # ─── Build App Database ───────────────────────────────────────────────

    def build_database(self) -> int:
        """
        Scan installed locations and build the app database.

        Returns:
            Number of apps indexed.
        """
        self._app_db = {}

        # Builtins
        for name, cmd in BUILTIN_APPS.items():
            self._app_db[name.lower()] = cmd

        # Scan shortcut folders (.lnk)
        for shortcut_dir in SHORTCUT_DIRS:
            self._scan_dir(shortcut_dir, recursive=True, extensions=[".lnk", ".exe"])

        # Scan Program Files
        for scan_dir in SCAN_DIRS:
            self._scan_dir(Path(scan_dir), recursive=False, extensions=[".exe"])

        self._db_built = True
        log.info("App database built: %d entries", len(self._app_db))
        return len(self._app_db)

    def _scan_dir(
        self,
        directory: Path,
        recursive: bool = True,
        extensions: Optional[list[str]] = None,
    ) -> None:
        """Scan a directory for application executables."""
        if not directory.exists():
            return
        extensions = extensions or [".exe", ".lnk"]

        try:
            iterator = directory.rglob("*") if recursive else directory.iterdir()
            for item in iterator:
                if item.suffix.lower() in extensions:
                    name = item.stem.lower()
                    # Clean up common suffixes
                    for suffix in (" - shortcut", " (2)", " (x86)", " (64-bit)"):
                        name = name.replace(suffix, "")
                    self._app_db[name.strip()] = str(item)
        except (PermissionError, OSError):
            pass

    # ─── Search & Launch ──────────────────────────────────────────────────

    def find(self, query: str) -> list[tuple[str, str]]:
        """
        Search for apps matching *query*.

        Args:
            query: Partial app name.

        Returns:
            List of (name, path) tuples, best match first.
        """
        if not self._db_built:
            self.build_database()

        query_lower = query.lower()
        all_names = list(self._app_db.keys())

        # Exact match first
        if query_lower in self._app_db:
            return [(query_lower, self._app_db[query_lower])]

        # Substring match
        substring = [(n, self._app_db[n]) for n in all_names if query_lower in n]
        if substring:
            return substring[:5]

        # Fuzzy match
        fuzzy_names = fuzzy_match(query_lower, all_names, threshold=0.5)
        return [(n, self._app_db[n]) for n in fuzzy_names[:5]]

    def launch(self, app_name: str) -> bool:
        """
        Launch an application by name.

        Args:
            app_name: Partial or full application name.

        Returns:
            True if launched successfully.
        """
        matches = self.find(app_name)
        if not matches:
            log.warning("App not found: %s", app_name)
            return False

        name, path = matches[0]
        log.info("Launching: %s (%s)", name, path)

        try:
            if path.startswith("ms-") or ":" in path and len(path.split(":")[0]) < 20:
                # Windows URI scheme
                os.startfile(path)  # type: ignore[attr-defined]
            elif path.endswith(".lnk") or path.endswith(".exe"):
                subprocess.Popen(
                    [path],
                    shell=False,
                    creationflags=subprocess.DETACHED_PROCESS
                    if hasattr(subprocess, "DETACHED_PROCESS") else 0,
                )
            else:
                subprocess.Popen(path, shell=True)

            if self._memory:
                self._memory.record_app_launch(name, path)

            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Launch failed for '%s': %s", app_name, exc)
            return False

    def get_all_apps(self) -> list[str]:
        """Return list of all known app names."""
        if not self._db_built:
            self.build_database()
        return sorted(self._app_db.keys())

    def is_running(self, app_name: str) -> bool:
        """
        Check if an app is currently running by name.

        Args:
            app_name: Application name to check.

        Returns:
            True if a matching process exists.
        """
        import psutil
        name_lower = app_name.lower()
        for proc in psutil.process_iter(["name"]):
            try:
                if name_lower in (proc.info["name"] or "").lower():
                    return True
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return False
