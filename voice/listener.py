"""
voice/listener.py — Offline speech recognition for JARVIS (Vosk)

Two modes:
1. wake_word_mode: Full STT triggered after wake word detected
2. push_to_talk: Listens on demand
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

log = get_logger("voice.listener")

SAMPLE_RATE = 16000
BLOCK_SIZE = 8000
SILENCE_CHUNKS = 3  # Chunks of silence before end-of-speech


class Listener:
    """
    Offline speech-to-text listener using Vosk.

    In wake_word_mode: waits for the WakeWordDetector signal,
    then captures and transcribes until silence.

    In push-to-talk mode: records for a fixed duration or until
    a stop signal.
    """

    def __init__(self) -> None:
        """Initialize the Vosk listener."""
        config = get_config()
        voice_cfg = config.get("voice", {})

        self._model_path = Path(
            voice_cfg.get("vosk_model_path", "models/vosk-model-small-en-us-0.15")
        )
        self._silence_timeout: float = voice_cfg.get("silence_timeout", 1.5)

        self._model: Optional[Model] = None
        self._listening = False
        self._status_callback: Optional[Callable[[str], None]] = None

        if not SOUNDDEVICE_AVAILABLE:
            log.warning("sounddevice not available. Voice input disabled.")
        if not VOSK_AVAILABLE:
            log.warning("vosk not available. Voice input disabled.")

        self._load_model()

    # ─── Model ────────────────────────────────────────────────────────────

    def _load_model(self) -> None:
        """Load the Vosk model from disk."""
        if not VOSK_AVAILABLE:
            return

        if not self._model_path.exists():
            log.warning(
                "Vosk model not found at %s. Run setup.bat to download it.",
                self._model_path,
            )
            return

        try:
            # Suppress Vosk's verbose output
            os.environ.setdefault("VOSK_LOG_LEVEL", "-1")
            self._model = Model(str(self._model_path))
            log.info("Vosk model loaded from %s", self._model_path)
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load Vosk model: %s", exc)

    @property
    def is_available(self) -> bool:
        """Return True if voice input is ready."""
        return VOSK_AVAILABLE and SOUNDDEVICE_AVAILABLE and self._model is not None

    # ─── Public API ───────────────────────────────────────────────────────

    def set_status_callback(self, callback: Callable[[str], None]) -> None:
        """
        Register a callback for status changes.

        Args:
            callback: Called with one of: 'idle', 'listening', 'processing'.
        """
        self._status_callback = callback

    def listen_once(self, timeout: float = 10.0) -> Optional[str]:
        """
        Listen for a single utterance and return transcribed text.

        Stops after *silence_timeout* seconds of silence or *timeout* total.

        Args:
            timeout: Maximum total listening time in seconds.

        Returns:
            Transcribed text or None on failure/timeout.
        """
        if not self.is_available:
            log.warning("Listener not available. Falling back to text input.")
            return None

        self._set_status("listening")
        log.info("Listening (timeout=%.1fs)…", timeout)

        audio_queue: queue.Queue = queue.Queue()

        def _callback(indata, frames, time_info, status):  # noqa: ARG001
            if status:
                log.debug("Audio status: %s", status)
            audio_queue.put(bytes(indata))

        recognizer = KaldiRecognizer(self._model, SAMPLE_RATE)
        result_text = ""
        silence_count = 0
        start_time = time.time()

        try:
            with sd.RawInputStream(
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                dtype="int16",
                channels=1,
                callback=_callback,
            ):
                while True:
                    if time.time() - start_time > timeout:
                        log.debug("Listener timeout reached.")
                        break

                    try:
                        data = audio_queue.get(timeout=0.5)
                    except queue.Empty:
                        silence_count += 1
                        if silence_count >= SILENCE_CHUNKS:
                            break
                        continue

                    if recognizer.AcceptWaveform(data):
                        res = json.loads(recognizer.Result())
                        text = res.get("text", "").strip()
                        if text:
                            result_text = text
                            silence_count = 0
                        else:
                            silence_count += 1
                    else:
                        partial = json.loads(recognizer.PartialResult())
                        partial_text = partial.get("partial", "").strip()
                        if partial_text:
                            silence_count = 0
                        else:
                            silence_count += 1

                    if silence_count >= SILENCE_CHUNKS and result_text:
                        break

        except Exception as exc:  # noqa: BLE001
            log.error("Listener error: %s", exc)

        self._set_status("processing" if result_text else "idle")
        log.info("Transcribed: '%s'", result_text)
        return result_text if result_text else None

    def listen_continuous(
        self,
        callback: Callable[[str], None],
        stop_event: Optional[threading.Event] = None,
    ) -> None:
        """
        Continuously listen and call *callback* with each utterance.

        Runs in the calling thread (block until stop_event is set).

        Args:
            callback: Called with each transcribed utterance.
            stop_event: Optional threading.Event to stop listening.
        """
        if not self.is_available:
            log.warning("Continuous listener not available.")
            return

        log.info("Starting continuous listener…")
        self._listening = True

        while self._listening:
            if stop_event and stop_event.is_set():
                break
            text = self.listen_once(timeout=30.0)
            if text:
                try:
                    callback(text)
                except Exception as exc:  # noqa: BLE001
                    log.error("Listener callback error: %s", exc)

        log.info("Continuous listener stopped.")

    def stop(self) -> None:
        """Signal the listener to stop."""
        self._listening = False
        self._set_status("idle")

    # ─── Internal ─────────────────────────────────────────────────────────

    def _set_status(self, status: str) -> None:
        if self._status_callback:
            try:
                self._status_callback(status)
            except Exception:  # noqa: BLE001
                pass
