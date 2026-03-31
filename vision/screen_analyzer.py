"""
vision/screen_analyzer.py — Screen analysis for JARVIS

Takes screenshots, runs OCR, detects active window,
identifies UI elements, errors, and frame changes.
"""

from __future__ import annotations

import re
import time
from typing import Optional

import numpy as np

try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False

from vision.screen_capture import ScreenCapture
from vision.ocr_engine import OCREngine
from utils.logger import get_logger

log = get_logger("vision.analyzer")

# ─── Patterns for error detection ─────────────────────────────────────────────

_ERROR_PATTERNS = re.compile(
    r"\b(error|exception|failed|failure|crash|not found|access denied"
    r"|cannot|unable to|warning|critical|fatal)\b",
    re.IGNORECASE,
)

_DIALOG_INDICATORS = [
    "ok", "cancel", "yes", "no", "retry", "abort", "ignore",
    "close", "apply", "accept", "deny", "continue", "skip",
]

_UI_BUTTON_REGEX = re.compile(
    r"\b(button|btn|click|press|submit|login|sign in|search|go|open|close"
    r"|save|load|next|back|done|finish|start|stop|play|pause)\b",
    re.IGNORECASE,
)


class ScreenAnalyzer:
    """
    Analyzes the current screen state for JARVIS perception layer.

    Returns structured data: active app, all visible text,
    UI elements, detected errors, and change detection.
    """

    def __init__(
        self,
        capture: Optional[ScreenCapture] = None,
        ocr: Optional[OCREngine] = None,
    ) -> None:
        """
        Initialize the screen analyzer.

        Args:
            capture: ScreenCapture instance (created if not provided).
            ocr: OCREngine instance (created if not provided).
        """
        self.capture = capture or ScreenCapture()
        self.ocr = ocr or OCREngine()
        self._prev_frame: Optional[np.ndarray] = None
        log.info("ScreenAnalyzer initialized.")

    # ─── Main Analysis ────────────────────────────────────────────────────

    def analyze(self) -> dict:
        """
        Perform a full screen analysis.

        Returns:
            Dict with keys:
                active_app (str): Title of the focused window.
                all_text (str): All visible text on screen.
                text_blocks (list): OCR blocks with positions.
                ui_elements (list): Detected interactive elements.
                errors_detected (bool): Whether error dialogs are visible.
                error_messages (list): Extracted error strings.
                changes (bool): Whether screen changed since last call.
                screenshot_path (str | None): Path to saved screenshot.
                timestamp (float): Unix timestamp.
        """
        ts = time.time()
        frame = self.capture.capture(as_numpy=True)
        screenshot_path = None

        if frame is None:
            log.warning("Screen capture returned None.")
            return self._empty_result(ts)

        # Save screenshot
        saved = self.capture.capture_to_file()
        if saved:
            screenshot_path = str(saved)

        # Change detection
        changed = False
        if self._prev_frame is not None:
            changed = self.capture.frames_differ(self._prev_frame, frame)
        self._prev_frame = frame

        # OCR
        text_blocks = self.ocr.extract_with_boxes(frame)
        all_text = " ".join(b["text"] for b in text_blocks if b["text"].strip())

        # Active window
        active_app = self._get_active_window()

        # UI element detection
        ui_elements = self._detect_ui_elements(text_blocks)

        # Error detection
        errors_detected, error_messages = self._detect_errors(all_text, text_blocks)

        result = {
            "active_app": active_app,
            "all_text": all_text,
            "text_blocks": text_blocks,
            "ui_elements": ui_elements,
            "errors_detected": errors_detected,
            "error_messages": error_messages,
            "changes": changed,
            "screenshot_path": screenshot_path,
            "timestamp": ts,
        }

        log.debug(
            "Screen analyzed: app=%s text_len=%d ui_elements=%d errors=%s",
            active_app,
            len(all_text),
            len(ui_elements),
            errors_detected,
        )
        return result

    def get_screen_text(self) -> str:
        """
        Quickly extract all visible text without full analysis.

        Returns:
            All visible text as a single string.
        """
        frame = self.capture.capture(as_numpy=True)
        if frame is None:
            return ""
        return self.ocr.extract_text(frame)

    def get_active_app(self) -> str:
        """
        Return the title of the currently active window.

        Returns:
            Window title string or empty string.
        """
        return self._get_active_window()

    def detect_popup(self) -> bool:
        """
        Check if a modal dialog or popup is visible on screen.

        Returns:
            True if a popup/dialog is detected.
        """
        text = self.get_screen_text()
        lowered = text.lower()
        indicator_count = sum(1 for ind in _DIALOG_INDICATORS if ind in lowered)
        return indicator_count >= 2  # At least 2 dialog buttons visible

    def find_text_on_screen(self, query: str) -> list[dict]:
        """
        Search the current screen for a specific text string.

        Args:
            query: Text to search for (case-insensitive).

        Returns:
            List of matching text block dicts (with bbox).
        """
        frame = self.capture.capture(as_numpy=True)
        if frame is None:
            return []
        blocks = self.ocr.extract_with_boxes(frame)
        return [
            b for b in blocks
            if query.lower() in b["text"].lower()
        ]

    # ─── Internal Helpers ─────────────────────────────────────────────────

    def _get_active_window(self) -> str:
        """Return the title of the focused window."""
        if PYGETWINDOW_AVAILABLE:
            try:
                win = gw.getActiveWindow()
                if win:
                    return win.title or ""
            except Exception:  # noqa: BLE001
                pass

        # Fallback: Windows-specific API
        try:
            import ctypes
            hwnd = ctypes.windll.user32.GetForegroundWindow()
            length = ctypes.windll.user32.GetWindowTextLengthW(hwnd)
            buf = ctypes.create_unicode_buffer(length + 1)
            ctypes.windll.user32.GetWindowTextW(hwnd, buf, length + 1)
            return buf.value
        except Exception:  # noqa: BLE001
            pass

        return ""

    def _detect_ui_elements(self, text_blocks: list[dict]) -> list[dict]:
        """
        Identify likely UI elements from OCR text blocks.

        Args:
            text_blocks: List of OCR result dicts.

        Returns:
            List of dicts with: type, text, bbox, confidence.
        """
        elements = []
        for block in text_blocks:
            text = block.get("text", "").strip()
            if not text:
                continue
            el_type = "text"
            if _UI_BUTTON_REGEX.search(text) or len(text) < 20:
                el_type = "button_or_label"
            if text.lower() in _DIALOG_INDICATORS:
                el_type = "dialog_button"
            elements.append({
                "type": el_type,
                "text": text,
                "bbox": block.get("bbox"),
                "confidence": block.get("confidence", 0.0),
            })
        return elements

    def _detect_errors(
        self,
        all_text: str,
        text_blocks: list[dict],
    ) -> tuple[bool, list[str]]:
        """
        Detect error dialogs or messages on screen.

        Args:
            all_text: Combined visible text.
            text_blocks: Individual OCR blocks.

        Returns:
            (errors_detected: bool, error_messages: list[str])
        """
        matches = _ERROR_PATTERNS.findall(all_text)
        if not matches:
            return False, []

        error_messages = []
        for block in text_blocks:
            if _ERROR_PATTERNS.search(block.get("text", "")):
                error_messages.append(block["text"])

        return bool(error_messages), error_messages

    @staticmethod
    def _empty_result(ts: float) -> dict:
        return {
            "active_app": "",
            "all_text": "",
            "text_blocks": [],
            "ui_elements": [],
            "errors_detected": False,
            "error_messages": [],
            "changes": False,
            "screenshot_path": None,
            "timestamp": ts,
        }
