"""
system/controller.py — Unified input controller for JARVIS

Wraps PyAutoGUI + keyboard library for mouse, keyboard,
and window management with human-like timing.
"""

from __future__ import annotations

import random
import time
from typing import Optional, Tuple

try:
    import pyautogui
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.05
    PYAUTOGUI_AVAILABLE = True
except ImportError:
    PYAUTOGUI_AVAILABLE = False

try:
    import keyboard as kb
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

try:
    import pygetwindow as gw
    PYGETWINDOW_AVAILABLE = True
except ImportError:
    PYGETWINDOW_AVAILABLE = False

from utils.helpers import get_config
from utils.logger import get_logger

log = get_logger("system.controller")

_DEFAULT_TYPE_SPEED = 0.03  # Seconds per character
_DEFAULT_MOVE_DURATION = 0.3  # Seconds for mouse moves


class SystemController:
    """
    Unified input controller for mouse, keyboard, and window management.

    All actions are logged. Screenshots can be taken before/after for
    verification. Human-like timing is applied to keyboard input.
    """

    def __init__(self) -> None:
        """Initialize the system controller."""
        config = get_config()
        sys_cfg = config.get("system", {})
        self._action_delay: float = sys_cfg.get("action_delay", 0.05)
        self._type_speed: float = sys_cfg.get("human_typing_speed", _DEFAULT_TYPE_SPEED)
        self._action_log: list[dict] = []

        if not PYAUTOGUI_AVAILABLE:
            log.warning("pyautogui not available. GUI control disabled.")

    # ─── Mouse ────────────────────────────────────────────────────────────

    def move(self, x: int, y: int, duration: float = _DEFAULT_MOVE_DURATION) -> bool:
        """
        Move the mouse to (x, y).

        Args:
            x: Target X coordinate.
            y: Target Y coordinate.
            duration: Move duration in seconds.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            pyautogui.moveTo(x, y, duration=duration, tween=pyautogui.easeInOutQuad)
            self._log_action("move", x=x, y=y)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Mouse move failed: %s", exc)
            return False

    def click(
        self,
        x: Optional[int] = None,
        y: Optional[int] = None,
        button: str = "left",
        clicks: int = 1,
    ) -> bool:
        """
        Click at (x, y) or at current position.

        Args:
            x: X coordinate (None = current position).
            y: Y coordinate (None = current position).
            button: 'left', 'right', or 'middle'.
            clicks: Number of clicks.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            kwargs = {"button": button, "clicks": clicks}
            if x is not None and y is not None:
                kwargs["x"] = x
                kwargs["y"] = y
            pyautogui.click(**kwargs)
            self._log_action("click", x=x, y=y, button=button)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Click failed: %s", exc)
            return False

    def double_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Double-click at (x, y)."""
        return self.click(x, y, clicks=2)

    def right_click(self, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """Right-click at (x, y)."""
        return self.click(x, y, button="right")

    def drag(
        self,
        x1: int,
        y1: int,
        x2: int,
        y2: int,
        duration: float = 0.5,
    ) -> bool:
        """
        Drag from (x1, y1) to (x2, y2).

        Args:
            x1, y1: Start position.
            x2, y2: End position.
            duration: Drag duration.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            pyautogui.drag(x2 - x1, y2 - y1, duration=duration, button="left")
            self._log_action("drag", x1=x1, y1=y1, x2=x2, y2=y2)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Drag failed: %s", exc)
            return False

    def scroll(self, clicks: int, x: Optional[int] = None, y: Optional[int] = None) -> bool:
        """
        Scroll up (positive) or down (negative).

        Args:
            clicks: Scroll amount (positive=up, negative=down).
            x, y: Optional coordinates to scroll at.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            if x is not None and y is not None:
                pyautogui.scroll(clicks, x=x, y=y)
            else:
                pyautogui.scroll(clicks)
            self._log_action("scroll", clicks=clicks)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Scroll failed: %s", exc)
            return False

    def get_mouse_position(self) -> Tuple[int, int]:
        """Return current mouse position."""
        if PYAUTOGUI_AVAILABLE:
            return pyautogui.position()
        return (0, 0)

    # ─── Keyboard ─────────────────────────────────────────────────────────

    def type_text(self, text: str, human_speed: bool = True) -> bool:
        """
        Type text with optional human-like timing.

        Args:
            text: Text to type.
            human_speed: If True, add random delays between keystrokes.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            if human_speed:
                for char in text:
                    pyautogui.typewrite(char, interval=0)
                    jitter = random.uniform(0, self._type_speed * 0.5)
                    time.sleep(self._type_speed + jitter)
            else:
                pyautogui.typewrite(text, interval=0.01)
            self._log_action("type", text=text[:50])
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Type failed: %s", exc)
            return False

    def press_key(self, key: str) -> bool:
        """
        Press a single key.

        Args:
            key: Key name (e.g. 'enter', 'escape', 'f5').

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            pyautogui.press(key)
            self._log_action("press_key", key=key)
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Key press failed: %s", exc)
            return False

    def hotkey(self, *keys: str) -> bool:
        """
        Press a key combination (e.g. hotkey('ctrl', 'c')).

        Args:
            *keys: Key names in order.

        Returns:
            True on success.
        """
        if not PYAUTOGUI_AVAILABLE:
            return False
        try:
            pyautogui.hotkey(*keys)
            self._log_action("hotkey", keys=list(keys))
            return True
        except Exception as exc:  # noqa: BLE001
            log.error("Hotkey failed: %s", exc)
            return False

    def hold_key(self, key: str, duration: float = 0.5) -> bool:
        """Hold a key for *duration* seconds."""
        if KEYBOARD_AVAILABLE:
            try:
                kb.press(key)
                time.sleep(duration)
                kb.release(key)
                return True
            except Exception as exc:  # noqa: BLE001
                log.error("Hold key failed: %s", exc)
        return False

    # ─── Windows ──────────────────────────────────────────────────────────

    def get_active_window(self) -> Optional[str]:
        """Return the title of the currently active window."""
        if PYGETWINDOW_AVAILABLE:
            try:
                win = gw.getActiveWindow()
                return win.title if win else None
            except Exception:  # noqa: BLE001
                pass
        return None

    def list_windows(self) -> list[str]:
        """Return titles of all open windows."""
        if PYGETWINDOW_AVAILABLE:
            try:
                return [w.title for w in gw.getAllWindows() if w.title]
            except Exception:  # noqa: BLE001
                pass
        return []

    def switch_to_window(self, title: str) -> bool:
        """
        Bring a window to the foreground by title.

        Args:
            title: Exact or partial window title.

        Returns:
            True if window was found and activated.
        """
        if not PYGETWINDOW_AVAILABLE:
            return False
        try:
            wins = gw.getWindowsWithTitle(title)
            if not wins:
                # Try partial match
                all_wins = gw.getAllWindows()
                wins = [w for w in all_wins if title.lower() in w.title.lower()]
            if wins:
                wins[0].activate()
                time.sleep(0.3)
                self._log_action("switch_window", title=title)
                return True
        except Exception as exc:  # noqa: BLE001
            log.error("Window switch failed: %s", exc)
        return False

    def minimize_window(self, title: Optional[str] = None) -> bool:
        """Minimize a window by title (or active window if None)."""
        if not PYGETWINDOW_AVAILABLE:
            return False
        try:
            if title:
                wins = gw.getWindowsWithTitle(title)
            else:
                wins = [gw.getActiveWindow()]
            if wins and wins[0]:
                wins[0].minimize()
                return True
        except Exception as exc:  # noqa: BLE001
            log.error("Minimize failed: %s", exc)
        return False

    def maximize_window(self, title: Optional[str] = None) -> bool:
        """Maximize a window by title (or active window if None)."""
        if not PYGETWINDOW_AVAILABLE:
            return False
        try:
            if title:
                wins = gw.getWindowsWithTitle(title)
            else:
                wins = [gw.getActiveWindow()]
            if wins and wins[0]:
                wins[0].maximize()
                return True
        except Exception as exc:  # noqa: BLE001
            log.error("Maximize failed: %s", exc)
        return False

    def close_window(self, title: Optional[str] = None) -> bool:
        """Close a window by title (or active window if None)."""
        if not PYGETWINDOW_AVAILABLE:
            return False
        try:
            if title:
                wins = gw.getWindowsWithTitle(title)
            else:
                wins = [gw.getActiveWindow()]
            if wins and wins[0]:
                wins[0].close()
                self._log_action("close_window", title=title)
                return True
        except Exception as exc:  # noqa: BLE001
            log.error("Window close failed: %s", exc)
        return False

    # ─── Screenshot ───────────────────────────────────────────────────────

    def take_screenshot(self, path: Optional[str] = None) -> Optional[str]:
        """
        Take a screenshot and return the saved path.

        Args:
            path: Optional save path. Auto-generated if None.

        Returns:
            Path string or None on failure.
        """
        if not PYAUTOGUI_AVAILABLE:
            return None
        try:
            import time as t
            if not path:
                from pathlib import Path
                Path("data/screenshots").mkdir(parents=True, exist_ok=True)
                path = f"data/screenshots/screenshot_{int(t.time())}.png"
            screenshot = pyautogui.screenshot()
            screenshot.save(path)
            log.info("Screenshot saved: %s", path)
            return path
        except Exception as exc:  # noqa: BLE001
            log.error("Screenshot failed: %s", exc)
            return None

    # ─── Action Log ───────────────────────────────────────────────────────

    def _log_action(self, action_type: str, **kwargs) -> None:
        """Record an action to the internal log."""
        import time as t
        entry = {"type": action_type, "timestamp": t.time(), **kwargs}
        self._action_log.append(entry)
        log.debug("Action: %s %s", action_type, kwargs)

    def get_action_log(self) -> list[dict]:
        """Return the full action log."""
        return list(self._action_log)

    def clear_action_log(self) -> None:
        """Clear the in-memory action log."""
        self._action_log.clear()
