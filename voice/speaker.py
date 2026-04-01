"""
voice/speaker.py — Text-to-speech for JARVIS (offline, via pyttsx3)

Features:
- TARS personality filter before speaking
- Configurable rate, volume, voice
- Priority-based speech queue
- Non-blocking playback in separate thread
- Interrupt support
"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass
from enum import IntEnum
from typing import Optional

try:
    import pyttsx3
    PYTTSX3_AVAILABLE = True
except ImportError:
    PYTTSX3_AVAILABLE = False

from utils.helpers import get_config
from utils.logger import get_logger
from utils.tars_personality import TARSPersonality

log = get_logger("voice.speaker")


class Priority(IntEnum):
    """Speech priority levels (lower number = higher priority)."""
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class _SpeechItem:
    """An item in the speech queue."""
    text: str
    priority: Priority
    apply_personality: bool = True


class Speaker:
    """
    Offline text-to-speech using pyttsx3.

    Maintains a priority queue of speech items and processes
    them in a dedicated background thread.
    """

    def __init__(
        self,
        personality: Optional[TARSPersonality] = None,
    ) -> None:
        """
        Initialize the speaker.

        Args:
            personality: TARSPersonality for response filtering.
        """
        config = get_config()
        voice_cfg = config.get("voice", {})

        self.enabled: bool = voice_cfg.get("enabled", True)
        self._rate: int = voice_cfg.get("rate", 175)
        self._volume: float = voice_cfg.get("volume", 0.9)
        self._voice_index: int = voice_cfg.get("voice_index", 0)

        self.personality = personality or TARSPersonality()
        self._engine: Optional[pyttsx3.Engine] = None
        self._queue: queue.PriorityQueue = queue.PriorityQueue()
        self._speaking = False
        self._stop_requested = False
        self._counter = 0  # For stable priority ordering
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        if self.enabled and PYTTSX3_AVAILABLE:
            self._init_engine()
            self._start_worker()
        elif not PYTTSX3_AVAILABLE:
            log.warning("pyttsx3 not available. Voice disabled.")
            self.enabled = False

    # ─── Public API ───────────────────────────────────────────────────────

    def speak(
        self,
        text: str,
        priority: Priority = Priority.NORMAL,
        apply_personality: bool = True,
        block: bool = False,
    ) -> None:
        """
        Queue text for speech synthesis.

        Args:
            text: Text to speak.
            priority: Speech priority.
            apply_personality: Whether to apply TARS personality filter.
            block: If True, wait until speech finishes.
        """
        if not self.enabled or not text.strip():
            print(f"JARVIS: {text}")
            return

        with self._lock:
            self._counter += 1
            item = _SpeechItem(text, priority, apply_personality)
            self._queue.put((priority.value, self._counter, item))

        log.debug("Queued speech [%s]: %s…", priority.name, text[:50])

        if block:
            self._queue.join()

    def speak_now(self, text: str) -> None:
        """Speak immediately with CRITICAL priority, interrupting current speech."""
        self.interrupt()
        self.speak(text, priority=Priority.CRITICAL, block=False)

    def interrupt(self) -> None:
        """Stop the currently playing speech."""
        if self._speaking and self._engine:
            try:
                self._stop_requested = True
                self._engine.stop()
            except Exception as exc:  # noqa: BLE001
                log.debug("Engine stop error: %s", exc)

    @property
    def is_speaking(self) -> bool:
        """Return True if speech is currently playing."""
        return self._speaking

    def set_rate(self, rate: int) -> None:
        """Change speech rate (words per minute)."""
        self._rate = rate
        if self._engine:
            self._engine.setProperty("rate", rate)

    def set_volume(self, volume: float) -> None:
        """Change speech volume (0.0–1.0)."""
        self._volume = max(0.0, min(1.0, volume))
        if self._engine:
            self._engine.setProperty("volume", self._volume)

    def list_voices(self) -> list[str]:
        """Return available voice names."""
        if not self._engine:
            return []
        return [v.name for v in self._engine.getProperty("voices")]

    def shutdown(self) -> None:
        """Stop the speaker worker thread."""
        self.enabled = False
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        log.info("Speaker shut down.")

    # ─── Internal ─────────────────────────────────────────────────────────

    def _init_engine(self) -> None:
        """Initialize pyttsx3 engine with configured settings."""
        try:
            self._engine = pyttsx3.init()
            self._engine.setProperty("rate", self._rate)
            self._engine.setProperty("volume", self._volume)

            voices = self._engine.getProperty("voices")
            if voices and 0 <= self._voice_index < len(voices):
                self._engine.setProperty("voice", voices[self._voice_index].id)

            log.info("pyttsx3 engine initialized. Rate=%d Vol=%.1f", self._rate, self._volume)
        except Exception as exc:  # noqa: BLE001
            log.error("pyttsx3 init failed: %s", exc)
            self.enabled = False

    def _start_worker(self) -> None:
        """Start background speech thread."""
        self._thread = threading.Thread(target=self._worker_loop, daemon=True)
        self._thread.start()

    def _worker_loop(self) -> None:
        """Process speech items from the queue."""
        while self.enabled or not self._queue.empty():
            try:
                _prio, _cnt, item = self._queue.get(timeout=0.5)
            except queue.Empty:
                continue

            text = item.text
            if item.apply_personality:
                text = self.personality.respond(text)

            self._say(text)
            self._queue.task_done()

    def _say(self, text: str) -> None:
        """Speak a single text string synchronously."""
        if not self._engine:
            print(f"JARVIS: {text}")
            return

        self._speaking = True
        self._stop_requested = False
        try:
            self._engine.say(text)
            self._engine.runAndWait()
        except Exception as exc:  # noqa: BLE001
            log.error("Speech error: %s", exc)
            print(f"JARVIS: {text}")
        finally:
            self._speaking = False
