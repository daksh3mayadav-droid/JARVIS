"""
interface/gui.py — System tray and floating overlay for JARVIS

Uses pystray for system tray icon and tkinter for optional
always-on-top floating widget. Toggle with Ctrl+Shift+J.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image as PILImage, ImageDraw
    PYSTRAY_AVAILABLE = True
except ImportError:
    PYSTRAY_AVAILABLE = False

try:
    import tkinter as tk
    from tkinter import ttk
    TK_AVAILABLE = True
except ImportError:
    TK_AVAILABLE = False

try:
    import keyboard
    KEYBOARD_AVAILABLE = True
except ImportError:
    KEYBOARD_AVAILABLE = False

from utils.helpers import get_config
from utils.logger import get_logger

log = get_logger("interface.gui")


class GUIManager:
    """
    System tray icon and optional floating overlay widget.

    Tray menu: Show/Hide, Status, Settings, Quit
    Floating overlay shows: listening status, current task, quick input.
    Toggle overlay: Ctrl+Shift+J
    """

    def __init__(
        self,
        on_quit: Optional[Callable] = None,
        on_command: Optional[Callable[[str], None]] = None,
    ) -> None:
        """
        Initialize the GUI manager.

        Args:
            on_quit: Callback invoked when user selects Quit from tray.
            on_command: Callback for commands entered in the overlay widget.
        """
        config = get_config()
        iface_cfg = config.get("interface", {})

        self._hotkey: str = iface_cfg.get("hotkey", "ctrl+shift+j")
        self._tray_icon_enabled: bool = iface_cfg.get("tray_icon", True)

        self._on_quit = on_quit
        self._on_command = on_command

        self._tray: Optional[pystray.Icon] = None
        self._overlay: Optional[tk.Toplevel] = None
        self._overlay_root: Optional[tk.Tk] = None
        self._overlay_visible = False
        self._status_text = "Idle"
        self._current_task = ""
        self._listening = False

        self._tray_thread: Optional[threading.Thread] = None
        self._tk_thread: Optional[threading.Thread] = None

        log.info("GUIManager initialized.")

    # ─── Tray Icon ────────────────────────────────────────────────────────

    def start_tray(self) -> None:
        """Start the system tray icon in a background thread."""
        if not PYSTRAY_AVAILABLE or not self._tray_icon_enabled:
            log.info("System tray unavailable or disabled.")
            return

        self._tray_thread = threading.Thread(
            target=self._run_tray, daemon=True
        )
        self._tray_thread.start()
        log.info("System tray started.")

    def _run_tray(self) -> None:
        """Build and run the pystray icon."""
        icon_image = self._make_tray_icon()

        menu = pystray.Menu(
            pystray.MenuItem("JARVIS — Active", None, enabled=False),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Show / Hide Overlay", self._toggle_overlay),
            pystray.MenuItem("System Status", self._show_tray_status),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit JARVIS", self._tray_quit),
        )

        self._tray = pystray.Icon(
            "JARVIS",
            icon_image,
            "JARVIS AI",
            menu=menu,
        )
        self._tray.run()

    def _make_tray_icon(self) -> "PILImage.Image":
        """Generate a simple blue 'J' tray icon."""
        size = 64
        img = PILImage.new("RGB", (size, size), color=(15, 20, 40))
        draw = ImageDraw.Draw(img)
        # Outer ring
        draw.ellipse([2, 2, size - 3, size - 3], outline=(0, 180, 255), width=3)
        # Letter J
        draw.text((22, 16), "J", fill=(0, 220, 255))
        return img

    def _toggle_overlay(self, icon=None, item=None) -> None:
        """Toggle overlay widget visibility."""
        if self._overlay_visible:
            self.hide_overlay()
        else:
            self.show_overlay()

    def _show_tray_status(self, icon=None, item=None) -> None:
        log.info("Tray status requested.")

    def _tray_quit(self, icon=None, item=None) -> None:
        """Handle Quit from tray menu."""
        if self._tray:
            self._tray.stop()
        if self._on_quit:
            self._on_quit()

    def update_tray_status(self, status: str) -> None:
        """Update tray tooltip text."""
        if self._tray:
            try:
                self._tray.title = f"JARVIS — {status}"
            except Exception:  # noqa: BLE001
                pass

    # ─── Floating Overlay ─────────────────────────────────────────────────

    def start_overlay(self) -> None:
        """Start the tkinter overlay in a background thread."""
        if not TK_AVAILABLE:
            log.info("tkinter unavailable. Overlay disabled.")
            return

        self._tk_thread = threading.Thread(
            target=self._run_tk, daemon=True
        )
        self._tk_thread.start()

        # Register global hotkey
        if KEYBOARD_AVAILABLE:
            try:
                keyboard.add_hotkey(self._hotkey, self._toggle_overlay)
                log.info("Hotkey registered: %s", self._hotkey)
            except Exception as exc:  # noqa: BLE001
                log.warning("Hotkey registration failed: %s", exc)

    def _run_tk(self) -> None:
        """Initialize and run the Tkinter root window."""
        try:
            self._overlay_root = tk.Tk()
            self._overlay_root.withdraw()  # Hidden root
            self._overlay_root.title("JARVIS")
            self._build_overlay()
            self._overlay_root.mainloop()
        except Exception as exc:  # noqa: BLE001
            log.error("Tkinter error: %s", exc)

    def _build_overlay(self) -> None:
        """Build the floating overlay Toplevel widget."""
        root = self._overlay_root
        self._overlay = tk.Toplevel(root)
        self._overlay.title("JARVIS")
        self._overlay.geometry("320x120+20+20")
        self._overlay.overrideredirect(True)  # Frameless
        self._overlay.attributes("-topmost", True)
        self._overlay.attributes("-alpha", 0.88)
        self._overlay.configure(bg="#0D1117")

        # Status label
        self._status_label = tk.Label(
            self._overlay,
            text="● JARVIS Active",
            fg="#00BFFF",
            bg="#0D1117",
            font=("Consolas", 10, "bold"),
        )
        self._status_label.pack(pady=(8, 0), padx=10, anchor="w")

        # Task label
        self._task_label = tk.Label(
            self._overlay,
            text="",
            fg="#888888",
            bg="#0D1117",
            font=("Consolas", 9),
        )
        self._task_label.pack(padx=10, anchor="w")

        # Input entry
        self._input_var = tk.StringVar()
        self._entry = tk.Entry(
            self._overlay,
            textvariable=self._input_var,
            bg="#1A1F2E",
            fg="#FFFFFF",
            insertbackground="#00BFFF",
            font=("Consolas", 10),
            relief="flat",
        )
        self._entry.pack(fill="x", padx=10, pady=(6, 0))
        self._entry.bind("<Return>", self._on_enter)

        # Drag support
        self._overlay.bind("<ButtonPress-1>", self._start_drag)
        self._overlay.bind("<B1-Motion>", self._do_drag)

        self._overlay.withdraw()  # Hidden by default

    def show_overlay(self) -> None:
        """Show the floating overlay."""
        if self._overlay and TK_AVAILABLE:
            try:
                self._overlay_root.after(0, self._overlay.deiconify)
                self._overlay_visible = True
            except Exception:  # noqa: BLE001
                pass

    def hide_overlay(self) -> None:
        """Hide the floating overlay."""
        if self._overlay and TK_AVAILABLE:
            try:
                self._overlay_root.after(0, self._overlay.withdraw)
                self._overlay_visible = False
            except Exception:  # noqa: BLE001
                pass

    def update_status(self, status: str, task: str = "") -> None:
        """
        Update the overlay status and current task text.

        Args:
            status: Short status string (e.g. 'Listening…', 'Processing').
            task: Current task description.
        """
        self._status_text = status
        self._current_task = task
        if self._overlay and TK_AVAILABLE:
            try:
                color = "#00FF7F" if "listen" in status.lower() else "#00BFFF"
                self._overlay_root.after(
                    0, lambda: self._status_label.configure(
                        text=f"● {status}", fg=color
                    )
                )
                self._overlay_root.after(
                    0, lambda: self._task_label.configure(text=task)
                )
            except Exception:  # noqa: BLE001
                pass

    # ─── Internal ─────────────────────────────────────────────────────────

    def _on_enter(self, event=None) -> None:
        """Handle Enter key in overlay input."""
        text = self._input_var.get().strip()
        if text and self._on_command:
            self._input_var.set("")
            threading.Thread(
                target=self._on_command, args=(text,), daemon=True
            ).start()

    def _start_drag(self, event) -> None:
        self._drag_x = event.x
        self._drag_y = event.y

    def _do_drag(self, event) -> None:
        if self._overlay:
            x = self._overlay.winfo_x() + event.x - self._drag_x
            y = self._overlay.winfo_y() + event.y - self._drag_y
            self._overlay.geometry(f"+{x}+{y}")

    def shutdown(self) -> None:
        """Stop the GUI manager."""
        if self._tray:
            try:
                self._tray.stop()
            except Exception:  # noqa: BLE001
                pass
        if self._overlay_root and TK_AVAILABLE:
            try:
                self._overlay_root.after(0, self._overlay_root.quit)
            except Exception:  # noqa: BLE001
                pass
        log.info("GUIManager shut down.")
