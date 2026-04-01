"""
main.py — JARVIS AI Assistant Boot Entry Point

Initializes all subsystems, starts wake word listener,
displays boot dashboard, and enters the main interaction loop.
"""

from __future__ import annotations

import signal
import sys
import threading
import time
from typing import Optional

# ─── Setup logging first ──────────────────────────────────────────────────────
from utils.logger import setup_logging, get_logger
from utils.helpers import get_config

config = get_config()
log_level = config.get("system", {}).get("log_level", "INFO")
setup_logging(log_level)

log = get_logger("main")

# ─── Subsystems ───────────────────────────────────────────────────────────────
from core.brain import Brain
from core.memory import Memory
from core.planner import Planner
from core.safety import SafetyClassifier
from system.controller import SystemController
from system.file_manager import FileManager
from system.process_manager import ProcessManager
from system.app_launcher import AppLauncher
from system.windows_navigator import WindowsNavigator
from system.hardware_info import HardwareInfo
from vision.screen_capture import ScreenCapture
from vision.screen_analyzer import ScreenAnalyzer
from voice.speaker import Speaker
from voice.listener import Listener
from voice.wake_word import WakeWordDetector
from interface.text_interface import TextInterface
from interface.gui import GUIManager
from automation.task_automator import TaskAutomator
from automation.browser_control import BrowserControl
from utils.tars_personality import TARSPersonality


# ─── JARVIS Application ───────────────────────────────────────────────────────

class JARVIS:
    """
    Top-level JARVIS AI assistant orchestrator.

    Connects all subsystems and runs the main interaction loop.
    Accepts voice (wake word → STT) and text input simultaneously.
    """

    def __init__(self) -> None:
        """Boot and wire all subsystems."""
        cfg = get_config()
        jarvis_cfg = cfg.get("jarvis", {})
        self.name = jarvis_cfg.get("name", "JARVIS")
        humor = jarvis_cfg.get("humor_level", 75)

        log.info("Booting %s…", self.name)

        # ── Personality & Memory ───────────────────────────────────────────
        self.personality = TARSPersonality(humor_level=humor)
        self.memory = Memory()

        # ── Core Reasoning ─────────────────────────────────────────────────
        self.safety = SafetyClassifier(
            safe_mode=cfg.get("system", {}).get("safe_mode", True),
            personality=self.personality,
        )
        self.planner = Planner(personality=self.personality)
        self.brain = Brain(
            memory=self.memory,
            planner=self.planner,
            safety=self.safety,
            personality=self.personality,
        )

        # ── System Control ─────────────────────────────────────────────────
        self.controller = SystemController()
        self.file_manager = FileManager(memory=self.memory)
        self.process_manager = ProcessManager()
        self.app_launcher = AppLauncher()
        self.app_launcher._memory = self.memory
        self.windows_nav = WindowsNavigator()
        self.hardware = HardwareInfo()

        # ── Vision ─────────────────────────────────────────────────────────
        self.screen_capture = ScreenCapture()
        self.screen_analyzer = ScreenAnalyzer(capture=self.screen_capture)

        # ── Voice ──────────────────────────────────────────────────────────
        self.speaker = Speaker(personality=self.personality)
        self.listener = Listener()
        self.wake_word_detector = WakeWordDetector()

        # ── Interface ──────────────────────────────────────────────────────
        self.ui = TextInterface()
        self.gui = GUIManager(
            on_quit=self.shutdown,
            on_command=self._handle_text_input,
        )

        # ── Automation ─────────────────────────────────────────────────────
        self.automator = TaskAutomator()
        self.automator.set_controller(self.controller)
        self.browser = BrowserControl()

        # ── Register action handlers in Brain ──────────────────────────────
        self._register_actions()

        # ── State ──────────────────────────────────────────────────────────
        self._running = False
        self._listening_active = False
        self._voice_thread: Optional[threading.Thread] = None

        log.info("All subsystems initialized.")

    # ─── Action Registry ──────────────────────────────────────────────────────

    def _register_actions(self) -> None:
        """Map action keys to handler callables for the Brain."""
        self.brain.register_actions({
            # System info
            "get_system_info": lambda: self._say_and_return(self.hardware.summary()),
            "get_cpu": lambda: self._say_and_return(
                f"CPU: {self.process_manager.get_cpu()['usage_pct']}%"
            ),
            "get_ram": lambda: self._say_and_return(
                f"RAM: {self.process_manager.get_ram()['used_human']} used"
            ),
            "get_gpu": lambda: self._say_and_return(
                str(self.process_manager.get_gpu())
            ),
            "get_battery": lambda: self._say_and_return(
                str(self.process_manager.get_battery())
            ),

            # App control
            "open_app": lambda app_name="": self._open_app(app_name),
            "close_app": lambda app_name="": self.process_manager.kill_process(app_name),

            # File operations
            "search_files": lambda query="", ext=None: self._search_files(query, ext),
            "list_dir": lambda path=".": self._list_dir(path),
            "take_screenshot": lambda: self._take_screenshot(),

            # Browser
            "open_url": lambda url="": self.browser.open_url(url),
            "google_search": lambda query="": self.browser.google_search(query),
            "youtube_search": lambda query="": self.browser.open_url(
                f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            ),
            "play_youtube": lambda query="": self.browser.open_url(
                f"https://www.youtube.com/results?search_query={query.replace(' ', '+')}"
            ),

            # Windows settings
            "open_settings": lambda page="": self.windows_nav.open_settings(page),
            "set_volume": lambda level=50: self.windows_nav.set_volume(int(level)),
            "set_brightness": lambda level=70: self.windows_nav.set_brightness(int(level)),
            "toggle_wifi": lambda: self.windows_nav.toggle_wifi(),
            "toggle_bluetooth": lambda: self.windows_nav.toggle_bluetooth(),
            "lock_screen": lambda: self.windows_nav.lock_screen(),

            # Input control
            "type_text": lambda text="": self.controller.type_text(text),
            "press_key": lambda key="": self.controller.press_key(key),
            "hotkey": lambda keys=[]: self.controller.hotkey(*keys),

            # Memory
            "remember": lambda topic="", content="": self.memory.store_knowledge(topic, content),
            "recall": lambda query="": self._recall(query),
        })

    # ─── Main Loop ────────────────────────────────────────────────────────────

    def run(self) -> None:
        """
        Start JARVIS: boot display, start services, enter interaction loop.
        """
        self._running = True

        # Boot screen
        self.ui.show_boot_screen()

        # Start wake word detector
        self.wake_word_detector.on_wake_word(self._on_wake_word)
        self.wake_word_detector.start()

        # Start system tray
        self.gui.start_tray()
        self.gui.start_overlay()

        # Greet
        self._speak("All systems online. How can I help?")

        # Main text input loop
        try:
            while self._running:
                try:
                    text = self.ui.get_input(">> ")
                except (EOFError, KeyboardInterrupt):
                    break

                if not text:
                    continue

                if text.lower() in ("quit", "exit", "shutdown"):
                    break
                elif text.lower() == "help":
                    self.ui.show_help()
                elif text.lower() == "clear":
                    self.ui.clear()
                elif text.lower() == "status":
                    self._show_status()
                else:
                    self._handle_text_input(text)

        except KeyboardInterrupt:
            pass

        self.shutdown()

    # ─── Input Handlers ───────────────────────────────────────────────────────

    def _handle_text_input(self, text: str) -> None:
        """Process a text command through the brain."""
        self.ui.print_user(text)
        self.gui.update_status("Processing…", text[:40])
        log.info("User input: %s", text)

        try:
            response = self.brain.process(text)
            self.ui.print_jarvis(response)
            self._speak(response, apply_personality=False)  # Already styled
        except Exception as exc:  # noqa: BLE001
            err = self.personality.error(str(exc))
            self.ui.error_message(err)
            self._speak(err, apply_personality=False)
            log.error("Input processing error: %s", exc)
        finally:
            self.gui.update_status("Idle")

    def _on_wake_word(self) -> None:
        """Called when wake word 'Jarvis' is detected."""
        if self._listening_active:
            return

        self._listening_active = True
        self.ui.system_message("🎤 Wake word detected — listening…")
        self.gui.update_status("Listening…")
        self._speak("Yes?", apply_personality=False)

        text = self.listener.listen_once(timeout=15.0)

        if text:
            self.ui.print_user(f"[Voice] {text}")
            self._handle_text_input(text)
        else:
            self.ui.system_message("Didn't catch that. Say 'Jarvis' to try again.")

        self._listening_active = False
        self.gui.update_status("Idle")

    # ─── Built-in Commands ────────────────────────────────────────────────────

    def _show_status(self) -> None:
        """Display current system status dashboard."""
        cpu = self.process_manager.get_cpu()
        ram = self.process_manager.get_ram()
        gpu_list = self.process_manager.get_gpu()
        battery = self.process_manager.get_battery()

        gpu_pct = gpu_list[0].get("load_pct", 0) if gpu_list else 0
        bat_pct = battery["percent"] if battery else 0

        self.ui.show_dashboard({
            "cpu_pct": cpu["usage_pct"],
            "ram_pct": ram["percent"],
            "gpu_pct": gpu_pct,
            "battery_pct": bat_pct,
            "uptime": self.hardware.get_os_info().get("uptime", "?"),
        })

        alerts = self.process_manager.check_alerts()
        for alert in alerts:
            self.ui.warning_message(alert)

    def _open_app(self, app_name: str) -> str:
        """Launch an application and return TARS response."""
        if self.app_launcher.launch(app_name):
            return self.personality.app_launch(app_name)
        return self.personality.not_found(app_name)

    def _search_files(self, query: str, ext: Optional[str] = None) -> str:
        """Search for files and display results."""
        results = self.file_manager.search(query, extension=ext, max_results=20)
        if not results:
            return self.personality.not_found(query)
        headers = ["Name", "Path", "Size", "Type"]
        rows = [
            [r["name"], r["path"][:50], r.get("size_human", "?"), r.get("extension", "")]
            for r in results[:10]
        ]
        self.ui.print_table(f"Search: '{query}'", headers, rows)
        return f"Found {len(results)} files matching '{query}'."

    def _list_dir(self, path: str) -> str:
        """List directory contents."""
        entries = self.file_manager.list_dir(path)
        if not entries:
            return f"No entries found at {path}."
        rows = [
            [e["name"], e["type"], e.get("size_human", ""), e.get("extension", "")]
            for e in entries[:20]
        ]
        self.ui.print_table(f"Directory: {path}", ["Name", "Type", "Size", "Ext"], rows)
        return f"{len(entries)} items in {path}."

    def _take_screenshot(self) -> str:
        """Take and save a screenshot."""
        path = self.controller.take_screenshot()
        if path:
            return f"Screenshot saved: {path}"
        return "Screenshot failed."

    def _recall(self, query: str) -> str:
        """Recall knowledge from memory."""
        results = self.memory.recall(query, limit=3)
        if not results:
            return "Nothing stored on that topic."
        return "\n".join(r["content"] for r in results)

    # ─── Speech ───────────────────────────────────────────────────────────────

    def _speak(self, text: str, apply_personality: bool = True) -> None:
        """Speak text via the speaker (non-blocking)."""
        self.speaker.speak(text, apply_personality=apply_personality)
        log.debug("Speaking: %s…", text[:60])

    def _say_and_return(self, text: str) -> str:
        """Speak and return the same text."""
        self._speak(text, apply_personality=False)
        return text

    # ─── Shutdown ─────────────────────────────────────────────────────────────

    def shutdown(self) -> None:
        """Gracefully shut down all JARVIS subsystems."""
        log.info("Shutting down JARVIS…")
        self._running = False

        self.wake_word_detector.stop()
        self.brain.shutdown()
        self.automator.shutdown()
        self.speaker.shutdown()
        self.gui.shutdown()
        self.memory.close()

        self.ui.system_message("JARVIS offline. Goodbye.")
        log.info("JARVIS shutdown complete.")


# ─── Entry Point ──────────────────────────────────────────────────────────────

def main() -> None:
    """Main entry point."""
    jarvis = JARVIS()

    # Handle Ctrl+C gracefully
    def _signal_handler(sig, frame):  # noqa: ARG001
        jarvis.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _signal_handler)

    jarvis.run()


if __name__ == "__main__":
    main()
