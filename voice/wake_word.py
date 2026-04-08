"""
voice/wake_word.py — Lightweight wake word detector for JARVIS

Runs in a background thread with minimal CPU (~2-5%).
Detects "Jarvis" using Vosk small model, then triggers callback.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import time
from pathlib import Path
from typing import Callable, Optional

try:
    import sounddevice as sd
    SOUNDDEVICE_AVAILABLE = True
except ImportError:
    SOUNDDEVICE_AVAILABLE = False

try:
    from vosk import Model, KaldiRecognizer
    VOSK_AVAILABLE = True
except ImportError:
    VOSK_AVAILABLE = False

from utils.helpers import get_config
from utils.logger import get_logger

log = get_logger("voice.wake_word")

SAMPLE_RATE = 16000
BLOCK_SIZE = 4000   # Smaller block for lower latency


class WakeWordDetector:
    """
    Lightweight background wake word detector.

    Uses the same Vosk model as the main listener.
    Calls the registered callback when the wake word is spoken.
    Visual/audio indicator fired on activation.
    """

    def __init__(self, model=None) -> None:
        """Initialize the wake word detector.

        Args:
            model: Optional pre-loaded Vosk Model instance. If provided,
                   it will be used directly instead of loading from disk.
        """
        config = get_config()
        voice_cfg = config.get("voice", {})

        self._wake_word: str = config.get("jarvis", {}).get(
            "wake_word", "jarvis"
        ).lower()
        self._model_path = Path(
            voice_cfg.get("vosk_model_path", "models/vosk-model-small-en-us-0.15")
        )
        self._activation_beep: bool = voice_cfg.get("activation_beep", True)

        self._active = False
        self._thread: Optional[threading.Thread] = None
        self._callbacks: list[Callable] = []
        self._cooldown = 2.0   # Seconds between activations

        if model is not None:
            self._model = model
            log.debug("Wake word detector using shared Vosk model.")
        else:
            self._model = None
            self._load_model()
        log.info("WakeWordDetector init. Wake word: '%s'", self._wake_word)

    # ─── Model ────────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Load Vosk model (shared with main listener)."""
        if not VOSK_AVAILABLE:
            return
        if not self._model_path.exists():
            log.warning("Vosk model missing. Wake word detection unavailable.")
            return
        try:
            os.environ.setdefault("VOSK_LOG_LEVEL", "-1")
            self._model = Model(str(self._model_path))
            log.debug("Wake word model loaded.")
        except Exception as exc:  # noqa: BLE001
            log.error("Wake word model load failed: %s", exc)

    @property
    def is_available(self) -> bool:
        """Return True if wake word detection is ready."""
        return VOSK_AVAILABLE and SOUNDDEVICE_AVAILABLE and self._model is not None

    # ─── Public API ───────────────────────────────────────────────────────

    def on_wake_word(self, callback: Callable) -> None:
        """
        Register a callback to fire when the wake word is detected.

        Args:
            callback: Zero-argument callable called on wake word detection.
        """
        self._callbacks.append(callback)

    def start(self) -> None:
        """Start the background wake word listener thread."""
        if not self.is_available:
            log.warning("Wake word detection unavailable (missing deps/model).")
            return
        if self._active:
            return
        self._active = True
        self._thread = threading.Thread(
            target=self._detection_loop, daemon=True
        )
        self._thread.start()
        log.info("Wake word detection started. Listening for '%s'…", self._wake_word)

    def stop(self) -> None:
        """Stop the background detector."""
        self._active = False
        if self._thread:
            self._thread.join(timeout=3)
        log.info("Wake word detector stopped.")

    @property
    def is_active(self) -> bool:
        """Return True if the detector is running."""
        return self._active

    def set_wake_word(self, word: str) -> None:
        """Dynamically change the wake word."""
        self._wake_word = word.lower()
        log.info("Wake word changed to '%s'", self._wake_word)

    # ─── Detection Loop ───────────────────────────────────────────────────

    def _detection_loop(self) -> None:
        """Background audio loop scanning for the wake word."""
        recognizer = KaldiRecognizer(self._model, SAMPLE_RATE)
        audio_queue: queue.Queue = queue.Queue(maxsize=10)
        last_trigger = 0.0

        def _audio_callback(indata, frames, time_info, status):  # noqa: ARG001
            if not audio_queue.full():
                audio_queue.put(bytes(indata))

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                dtype="int16",
                channels=1,
                callback=_audio_callback,
            ):
                while self._active:
                    try:
                        data = audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        continue

                    if recognizer.AcceptWaveform(data):
                        result = json.loads(recognizer.Result())
                        text = result.get("text", "").lower()
                        now = time.time()

                        if (
                            self._wake_word in text
                            and now - last_trigger > self._cooldown
                        ):
                            last_trigger = now
                            log.info("Wake word detected!")
                            self._on_detected()

        except Exception as exc:  # noqa: BLE001
            log.error("Wake word detection loop error: %s", exc)
            self._active = False

    def _on_detected(self) -> None:
        """Handle wake word detection: beep + callbacks."""
        if self._activation_beep:
            self._play_beep()

        log.info("Triggering %d wake word callback(s).", len(self._callbacks))
        for cb in self._callbacks:
            try:
                threading.Thread(target=cb, daemon=True).start()
            except Exception as exc:  # noqa: BLE001
                log.error("Wake word callback error: %s", exc)

    @staticmethod
    def _play_beep() -> None:
        """Play a short activation beep (Windows only)."""
        try:
            import winsound
            winsound.Beep(880, 200)   # 880 Hz for 200ms
        except ImportError:
            pass  # Non-Windows: silent activation
        except Exception:  # noqa: BLE001
            pass
