"""
automation/browser_control.py — Browser automation for JARVIS

Opens browser URLs, performs Google searches, navigates tabs,
fills forms, and reads page content via OCR.
"""

from __future__ import annotations

import subprocess
import time
import webbrowser
from typing import Optional
from urllib.parse import quote_plus

try:
    import pyautogui
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

from utils.logger import get_logger

log = get_logger("automation.browser")

# ─── Common browser hotkeys (Windows) ────────────────────────────────────────

_BROWSER_SHORTCUTS = {
    "new_tab":       ("ctrl", "t"),
    "close_tab":     ("ctrl", "w"),
    "new_window":    ("ctrl", "n"),
    "refresh":       ("ctrl", "r"),
    "hard_refresh":  ("ctrl", "shift", "r"),
    "back":          ("alt", "Left"),
    "forward":       ("alt", "Right"),
    "address_bar":   ("ctrl", "l"),
    "find":          ("ctrl", "f"),
    "bookmarks":     ("ctrl", "d"),
    "history":       ("ctrl", "h"),
    "downloads":     ("ctrl", "j"),
    "settings":      ("ctrl", ","),
    "zoom_in":       ("ctrl", "+"),
    "zoom_out":      ("ctrl", "-"),
    "zoom_reset":    ("ctrl", "0"),
    "full_screen":   ("F11",),
    "developer":     ("F12",),
    "next_tab":      ("ctrl", "Tab"),
    "prev_tab":      ("ctrl", "shift", "Tab"),
    "reopen_tab":    ("ctrl", "shift", "t"),
    "print":         ("ctrl", "p"),
    "save_page":     ("ctrl", "s"),
}


class BrowserControl:
    """
    Browser automation via PyAutoGUI keyboard shortcuts and
    webbrowser/subprocess for launching.

    Reads page content via screen capture + OCR.
    """

    def __init__(self) -> None:
        """Initialize the browser controller."""
        if not PYAUTOGUI_AVAILABLE:
            log.warning("pyautogui not available. Browser keyboard control disabled.")
        log.info("BrowserControl initialized.")

    # ─── Launch ───────────────────────────────────────────────────────────

    def open_url(self, url: str) -> bool:
        """
        Open a URL in the default browser.

        Args:
            url: Full URL (http:// prefix added if missing).

        Returns:
            True on success.
        """
        if not url.startswith(("http://", "https://", "file://")):
            url = "https://" + url
        try:
            webbrowser.open(url)
            log.info("Opened URL: %s", url)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Open URL failed: %s", exc)
            return False

    def google_search(self, query: str) -> bool:
        """
        Open Google search for the given query.

        Args:
            query: Search query string.

        Returns:
            True on success.
        """
        url = f"https://www.google.com/search?q={quote_plus(query)}"
        return self.open_url(url)

    def youtube_search(self, query: str) -> bool:
        """Open YouTube search."""
        url = f"https://www.youtube.com/results?search_query={quote_plus(query)}"
        return self.open_url(url)

    def open_browser(self, browser: str = "default") -> bool:
        """
        Open a specific browser application.

        Args:
            browser: 'chrome', 'firefox', 'edge', or 'default'.

        Returns:
            True on success.
        """
        browser_commands = {
            "chrome": ["chrome", "google-chrome", r"C:\Program Files\Google\Chrome\Application\chrome.exe"],
            "firefox": ["firefox", r"C:\Program Files\Mozilla Firefox\firefox.exe"],
            "edge": ["msedge", r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"],
        }

        if browser == "default":
            webbrowser.open("about:blank")
            return True

        commands = browser_commands.get(browser.lower(), [])
        for cmd in commands:
            try:
                subprocess.Popen([cmd], shell=False)
                log.info("Launched browser: %s", browser)
                return True
            except FileNotFoundError:
                continue

        # Shell fallback
        try:
            subprocess.Popen(browser, shell=True)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Browser launch failed: %s", exc)
            return False

    # ─── Navigation ───────────────────────────────────────────────────────

    def navigate(self, action: str) -> bool:
        """
        Perform a browser navigation action.

        Args:
            action: One of the keys in _BROWSER_SHORTCUTS.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        keys = _BROWSER_SHORTCUTS.get(action.lower().replace(" ", "_"))
        if not keys:
            log.warning("Unknown browser action: %s", action)
            return False
        try:
            pyautogui.hotkey(*keys)
            log.debug("Browser action: %s", action)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Browser navigation failed: %s", exc)
            return False

    def go_back(self) -> bool:
        """Navigate back."""
        return self.navigate("back")

    def go_forward(self) -> bool:
        """Navigate forward."""
        return self.navigate("forward")

    def refresh(self) -> bool:
        """Refresh the current page."""
        return self.navigate("refresh")

    def new_tab(self, url: str = "") -> bool:
        """Open a new tab, optionally at *url*."""
        if not self.navigate("new_tab"):
            return False
        if url:
            time.sleep(0.5)
            self.navigate_to_url_in_bar(url)
        return True

    def close_tab(self) -> bool:
        """Close the current tab."""
        return self.navigate("close_tab")

    def next_tab(self) -> bool:
        """Switch to the next tab."""
        return self.navigate("next_tab")

    def prev_tab(self) -> bool:
        """Switch to the previous tab."""
        return self.navigate("prev_tab")

    def navigate_to_url_in_bar(self, url: str) -> bool:
        """
        Type a URL into the browser address bar.

        Args:
            url: URL to navigate to.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            pyautogui.hotkey("ctrl", "l")  # Focus address bar
            time.sleep(0.3)
            pyautogui.hotkey("ctrl", "a")  # Select all
            pyautogui.typewrite(url, interval=0.03)
            pyautogui.press("enter")
            log.info("Navigated to: %s", url)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("URL navigation failed: %s", exc)
            return False

    # ─── Form Filling ─────────────────────────────────────────────────────

    def fill_form_field(
        self,
        x: int,
        y: int,
        text: str,
        clear_first: bool = True,
    ) -> bool:
        """
        Click a form field at (x, y) and type text.

        Args:
            x, y: Coordinates of the form field.
            text: Text to type.
            clear_first: If True, Ctrl+A before typing.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            pyautogui.click(x, y)
            time.sleep(0.2)
            if clear_first:
                pyautogui.hotkey("ctrl", "a")
            pyautogui.typewrite(text, interval=0.04)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Form fill failed: %s", exc)
            return False

    def submit_form(self) -> bool:
        """Press Enter to submit the current form."""
        if not PYAUTOGUI_AVAILABLE:
            return False
        pyautogui.press("enter")
        return True

    # ─── Page Content ─────────────────────────────────────────────────────

    def read_page_text(self) -> str:
        """
        Extract visible text from the current browser page using OCR.

        Returns:
            OCR-extracted text string.
        """
        try:
            from vision.screen_capture import ScreenCapture
            from vision.ocr_engine import OCREngine
            capture = ScreenCapture()
            ocr = OCREngine()
            frame = capture.capture(as_numpy=True)
            if frame is None:
                return ""
            return ocr.extract_text(frame)
        except Exception as exc:  # noqa: BLE001
            log.error("Page text read failed: %s", exc)
            return ""

    # ─── Bookmarks ────────────────────────────────────────────────────────

    def bookmark_page(self) -> bool:
        """Bookmark the current page (Ctrl+D)."""
        return self.navigate("bookmarks")

    def open_history(self) -> bool:
        """Open browser history."""
        return self.navigate("history")

    def open_downloads(self) -> bool:
        """Open browser downloads."""
        return self.navigate("downloads")
