"""
main.py — JARVIS AI Assistant Boot Entry Point

Initializes all subsystems, starts wake word listener,
displays boot dashboard, and enters the main interaction loop.
"""

from __future__ import annotations

import os
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

# ─── Core subsystems (always needed at startup) ───────────────────────────────
from core.brain import Brain
from core.memory import Memory
from core.planner import Planner
from core.safety import SafetyClassifier
from system.controller import SystemController
from system.process_manager import ProcessManager
from system.app_launcher import AppLauncher
from system.windows_navigator import WindowsNavigator
from voice.speaker import Speaker
from voice.listener import Listener
from voice.wake_word import WakeWordDetector
from interface.text_interface import TextInterface
from interface.gui import GUIManager
from utils.tars_personality import TARSPersonality


# ─── JARVIS Application ───────────────────────────────────────────────────────

# Conversational auto-listen settings
_MAX_CONVERSATIONAL_FOLLOW_UPS = 3   # max back-to-back auto-listens after a question
_FOLLOW_UP_LISTEN_TIMEOUT = 10.0     # seconds to wait for each follow-up utterance

class JARVIS:
    """
    Top-level JARVIS AI assistant orchestrator.

    Connects all subsystems and runs the main interaction loop.
    Accepts voice (wake word → STT) and text input simultaneously.

    Heavy subsystems (ScreenCapture, ScreenAnalyzer, BrowserControl,
    TaskAutomator, FileManager, HardwareInfo) are lazy-loaded on first use
    to keep startup fast.
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
        self.process_manager = ProcessManager()
        self.app_launcher = AppLauncher()
        self.app_launcher._memory = self.memory
        self.windows_nav = WindowsNavigator()

        # ── Lazy-loaded heavy subsystems (initialized to None) ─────────────
        self._hardware = None
        self._screen_capture = None
        self._screen_analyzer = None
        self._file_manager = None
        self._automator = None
        self._browser = None
        self._youtube = None
        self._music_player = None

        # ── Voice ──────────────────────────────────────────────────────────
        # Load Vosk model once and share between Listener and WakeWordDetector
        vosk_model = None
        try:
            from vosk import Model as VoskModel
            from pathlib import Path
            vosk_model_path = cfg.get("voice", {}).get(
                "vosk_model_path", "models/vosk-model-small-en-us-0.15"
            )
            if Path(vosk_model_path).exists():
                os.environ.setdefault("VOSK_LOG_LEVEL", "-1")
                vosk_model = VoskModel(vosk_model_path)
                log.info("Shared Vosk model loaded from %s", vosk_model_path)
        except ImportError:
            pass

        self.speaker = Speaker(personality=self.personality)
        self.listener = Listener(model=vosk_model)
        self.wake_word_detector = WakeWordDetector(model=vosk_model)

        # ── Interface ──────────────────────────────────────────────────────
        self.ui = TextInterface()
        self.gui = GUIManager(
            on_quit=self.shutdown,
            on_command=self._handle_text_input,
        )

        # ── Register action handlers in Brain ──────────────────────────────
        self._register_actions()

        # ── State ──────────────────────────────────────────────────────────
        self._running = False
        self._listening_active = False
        self._voice_thread: Optional[threading.Thread] = None

        log.info("All subsystems initialized.")

    # ─── Lazy-loaded Properties ───────────────────────────────────────────────

    @property
    def hardware(self):
        """Lazy-load HardwareInfo on first access."""
        if self._hardware is None:
            from system.hardware_info import HardwareInfo
            self._hardware = HardwareInfo()
        return self._hardware

    @property
    def screen_capture(self):
        """Lazy-load ScreenCapture on first access."""
        if self._screen_capture is None:
            from vision.screen_capture import ScreenCapture
            self._screen_capture = ScreenCapture()
        return self._screen_capture

    @property
    def screen_analyzer(self):
        """Lazy-load ScreenAnalyzer (and ScreenCapture) on first access."""
        if self._screen_analyzer is None:
            from vision.screen_analyzer import ScreenAnalyzer
            self._screen_analyzer = ScreenAnalyzer(capture=self.screen_capture)
        return self._screen_analyzer

    @property
    def file_manager(self):
        """Lazy-load FileManager on first access."""
        if self._file_manager is None:
            from system.file_manager import FileManager
            self._file_manager = FileManager(memory=self.memory)
        return self._file_manager

    @property
    def automator(self):
        """Lazy-load TaskAutomator on first access."""
        if self._automator is None:
            from automation.task_automator import TaskAutomator
            self._automator = TaskAutomator()
            self._automator.set_controller(self.controller)
        return self._automator

    @property
    def browser(self):
        """Lazy-load BrowserControl on first access."""
        if self._browser is None:
            from automation.browser_control import BrowserControl
            self._browser = BrowserControl()
        return self._browser

    @property
    def youtube(self):
        """Lazy-load YouTubeController on first access."""
        if self._youtube is None:
            from automation.youtube_control import YouTubeController
            self._youtube = YouTubeController(self.controller, self.browser)
        return self._youtube

    @property
    def music_player(self):
        """Lazy-load MusicPlayer on first access."""
        if self._music_player is None:
            from automation.music_player import MusicPlayer
            self._music_player = MusicPlayer()
        return self._music_player

    # ─── Action Registry ──────────────────────────────────────────────────────

    def _register_actions(self) -> None:
        """Map action keys to handler callables for the Brain."""
        self.brain.register_actions({
            # System info
            "get_system_info": lambda: self._say_and_return(self.hardware.summary()),
            "get_cpu": lambda: self._say_and_return(
                f"CPU: {self.process_manager.get_cpu().get('percent', 0.0):.1f}%"
            ),
            "get_ram": lambda: self._say_and_return(
                f"RAM: {self.process_manager.get_ram().get('used_human', '?')} used"
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
            "youtube_search": lambda query="": self.youtube.search(query),
            "play_youtube": lambda query="": self.youtube.search_and_play(query) if query else self.youtube.open_youtube(),

            # YouTube — Playback
            "yt_play_pause":    lambda: self.youtube.play_pause(),
            "yt_play":          lambda: self.youtube.play(),
            "yt_pause":         lambda: self.youtube.pause(),
            "yt_skip_forward":  lambda seconds=5: self.youtube.skip_forward(int(seconds)),
            "yt_skip_backward": lambda seconds=5: self.youtube.skip_backward(int(seconds)),
            "yt_next_video":    lambda: self.youtube.next_video(),
            "yt_previous_video": lambda: self.youtube.previous_video(),
            "yt_restart":       lambda: self.youtube.restart_video(),

            # YouTube — Volume
            "yt_volume_up":   lambda: self.youtube.volume_up(),
            "yt_volume_down": lambda: self.youtube.volume_down(),
            "yt_mute":        lambda: self.youtube.mute_unmute(),

            # YouTube — Display
            "yt_fullscreen":      lambda: self.youtube.fullscreen(),
            "yt_exit_fullscreen": lambda: self.youtube.exit_fullscreen(),
            "yt_theater":         lambda: self.youtube.theater_mode(),
            "yt_miniplayer":      lambda: self.youtube.miniplayer(),

            # YouTube — Captions & Speed
            "yt_captions":      lambda: self.youtube.toggle_captions(),
            "yt_speed_up":      lambda: self.youtube.speed_up(),
            "yt_slow_down":     lambda: self.youtube.slow_down(),
            "yt_normal_speed":  lambda: self.youtube.normal_speed(),
            "yt_speed": lambda speed="normal": (
                self.youtube.speed_up() if speed == "fast" else
                self.youtube.slow_down() if speed == "slow" else
                self.youtube.normal_speed()
            ),

            # YouTube — Navigation
            "yt_home":          lambda: self.youtube.open_youtube(),
            "yt_trending":      lambda: self.youtube.open_trending(),
            "yt_subscriptions": lambda: self.youtube.open_subscriptions(),
            "yt_history":       lambda: self.youtube.open_history(),
            "yt_liked":         lambda: self.youtube.open_liked_videos(),
            "yt_watch_later":   lambda: self.youtube.open_watch_later(),
            "yt_shorts":        lambda: self.youtube.open_shorts(),
            "yt_music":         lambda: self.youtube.open_music(),
            "yt_search":        lambda query="": self.youtube.search(query),
            "yt_timestamp":     lambda position=5: self.youtube.go_to_timestamp(int(position)),
            "yt_skip_ad":       lambda: self.youtube.skip_ad(),

            # Windows settings
            "open_settings": lambda page="": self.windows_nav.open_settings(page),
            "set_volume": lambda level=50: self.windows_nav.set_volume(int(level)),
            "set_brightness": lambda level=70: self.windows_nav.set_brightness(int(level)),
            "toggle_wifi": lambda: self.windows_nav.toggle_wifi(),
            "toggle_bluetooth": lambda: self.windows_nav.toggle_bluetooth(),
            "lock_screen": lambda: self.windows_nav.lock_screen(),

            # Mouse control
            "click":        lambda: self.controller.click(),
            "mouse_click":  lambda: self.controller.click(),
            "right_click":  lambda: self.controller.right_click(),
            "double_click": lambda: self.controller.double_click(),
            "scroll_up":    lambda: self.controller.scroll(3),
            "scroll_down":  lambda: self.controller.scroll(-3),

            # Window control
            "minimize_window": lambda: self.controller.hotkey("win", "down"),
            "maximize_window": lambda: self.controller.hotkey("win", "up"),
            "close_window":    lambda: self.controller.hotkey("alt", "F4"),
            "switch_window":   lambda: self.controller.hotkey("alt", "tab"),
            "snap_left":       lambda: self.controller.hotkey("win", "left"),
            "snap_right":      lambda: self.controller.hotkey("win", "right"),
            "show_desktop":    lambda: self.controller.hotkey("win", "d"),
            "task_view":       lambda: self.controller.hotkey("win", "tab"),

            # Browser tab control
            "new_tab":      lambda: self.browser.new_tab(),
            "close_tab":    lambda: self.browser.close_tab(),
            "next_tab":     lambda: self.browser.next_tab(),
            "prev_tab":     lambda: self.browser.prev_tab(),
            "refresh_page": lambda: self.browser.refresh(),
            "go_back":      lambda: self.browser.go_back(),
            "go_forward":   lambda: self.browser.go_forward(),

            # Input control
            "type_text": lambda text="": self.controller.type_text(text),
            "press_key": lambda key="": self.controller.press_key(key),
            "hotkey": lambda keys=[]: self.controller.hotkey(*keys),

            # Memory
            "remember": lambda topic="", content="": self.memory.store_knowledge(topic, content),
            "recall": lambda query="": self._recall(query),

            # Music streaming (no browser — pure audio via yt-dlp + mpv)
            "play_music":       lambda query="": self.music_player.play(query),
            "music_pause":      lambda: self.music_player.pause(),
            "music_resume":     lambda: self.music_player.resume(),
            "music_stop":       lambda: self.music_player.stop(),
            "music_skip":       lambda: self.music_player.skip(),
            "music_volume":     lambda level=50: self.music_player.set_volume(int(level)),
            "music_now_playing": lambda: self.music_player.now_playing or "Nothing is playing.",
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

    def _handle_text_input_return(self, text: str) -> str:
        """Process a text command through the brain and return the response string."""
        self.ui.print_user(text)
        self.gui.update_status("Processing…", text[:40])
        log.info("User input: %s", text)
        try:
            response = self.brain.process(text)
            self.ui.print_jarvis(response)
            self._speak(response, apply_personality=False)
            return response
        except Exception as exc:  # noqa: BLE001
            err = self.personality.error(str(exc))
            self.ui.error_message(err)
            self._speak(err, apply_personality=False)
            log.error("Input processing error: %s", exc)
            return err
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
            response = self._handle_text_input_return(text)

            # Conversational mode: if JARVIS asked a question, auto-listen
            follow_up_count = 0
            while (
                response
                and response.rstrip().endswith("?")
                and follow_up_count < _MAX_CONVERSATIONAL_FOLLOW_UPS
            ):
                self.ui.system_message("🎤 Listening for follow-up…")
                self.gui.update_status("Listening…")
                follow_text = self.listener.listen_once(timeout=_FOLLOW_UP_LISTEN_TIMEOUT)
                if not follow_text:
                    break
                self.ui.print_user(f"[Voice] {follow_text}")
                response = self._handle_text_input_return(follow_text)
                follow_up_count += 1
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
            "cpu_pct": cpu.get("percent", 0),
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
        if self._automator is not None:
            self._automator.shutdown()
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
