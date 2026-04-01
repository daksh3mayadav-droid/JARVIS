"""
vision/screen_capture.py — Real-time screen capture for JARVIS

Uses mss for fast screen capture. Supports full-screen,
region-of-interest capture, and continuous monitoring mode.
"""

from __future__ import annotations

import threading
import time
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np

try:
    import mss
    MSS_AVAILABLE = True
except ImportError:
    MSS_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from utils.helpers import get_config
from utils.logger import get_logger

log = get_logger("vision.capture")

# Screenshot save directory
_DEFAULT_SAVE_DIR = Path("data/screenshots")


class ScreenCapture:
    """
    Real-time screen capture using mss.

    Supports:
    - Full-screen and region-of-interest capture
    - Continuous monitoring at configurable FPS
    - Frame differencing for change detection
    - PIL Image or numpy array output
    """

    def __init__(self) -> None:
        """Initialize the screen capture module."""
        config = get_config()
        vision_cfg = config.get("vision", {})

        self.fps: float = vision_cfg.get("capture_fps", 1)
        self._save_dir = Path(
            vision_cfg.get("screenshot_dir", str(_DEFAULT_SAVE_DIR))
        )
        self._save_dir.mkdir(parents=True, exist_ok=True)

        self._monitoring = False
        self._monitor_thread: Optional[threading.Thread] = None
        self._last_frame: Optional[np.ndarray] = None
        self._change_threshold: int = vision_cfg.get("change_threshold", 30)

        if not MSS_AVAILABLE:
            log.warning("mss not available. Screen capture disabled.")
        if not PIL_AVAILABLE:
            log.warning("Pillow not available. Image conversion limited.")

        log.info("ScreenCapture initialized. FPS: %s", self.fps)

    # ─── Single Capture ───────────────────────────────────────────────────

    def capture(
        self,
        region: Optional[Tuple[int, int, int, int]] = None,
        as_numpy: bool = False,
    ) -> Optional["Image.Image | np.ndarray"]:
        """
        Capture the screen or a region.

        Args:
            region: (left, top, width, height) in pixels. None = full screen.
            as_numpy: If True, return numpy array; else PIL Image.

        Returns:
            PIL Image, numpy array, or None on failure.
        """
        if not MSS_AVAILABLE:
            log.error("mss not installed. Cannot capture.")
            return None

        try:
            with mss.mss() as sct:
                monitor = self._get_monitor(sct, region)
                screenshot = sct.grab(monitor)
                arr = np.array(screenshot)

                if as_numpy:
                    return arr

                if PIL_AVAILABLE:
                    # mss returns BGRA; convert to RGB
                    img = Image.fromarray(arr[:, :, :3][..., ::-1])
                    return img

                return arr

        except Exception as exc:  # noqa: BLE001
            log.error("Screen capture failed: %s", exc)
            return None

    def capture_to_file(
        self,
        path: Optional[Path] = None,
        region: Optional[Tuple[int, int, int, int]] = None,
    ) -> Optional[Path]:
        """
        Capture the screen and save to a PNG file.

        Args:
            path: Save path. Auto-generated timestamp name if None.
            region: Optional capture region.

        Returns:
            Path to saved file or None on failure.
        """
        img = self.capture(region=region, as_numpy=False)
        if img is None:
            return None

        if path is None:
            ts = int(time.time())
            path = self._save_dir / f"screenshot_{ts}.png"

        try:
            if PIL_AVAILABLE:
                img.save(str(path))  # type: ignore[union-attr]
            else:
                log.error("Pillow not available. Cannot save image.")
                return None
            log.debug("Screenshot saved: %s", path)
            return path
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to save screenshot: %s", exc)
            return None

    def get_screen_size(self) -> Tuple[int, int]:
        """
        Return the primary monitor resolution.

        Returns:
            (width, height) tuple.
        """
        if not MSS_AVAILABLE:
            return (1920, 1080)  # Default assumption
        try:
            with mss.mss() as sct:
                mon = sct.monitors[1]
                return (mon["width"], mon["height"])
        except Exception:  # noqa: BLE001
            return (1920, 1080)

    # ─── Continuous Monitoring ────────────────────────────────────────────

    def start_monitoring(
        self,
        callback: Callable[[np.ndarray], None],
        region: Optional[Tuple[int, int, int, int]] = None,
        detect_changes: bool = True,
    ) -> None:
        """
        Start background continuous screen capture.

        Args:
            callback: Called with each new frame (numpy array).
            region: Optional capture region.
            detect_changes: If True, only call callback when frame changes.
        """
        if self._monitoring:
            log.warning("Monitoring already active.")
            return

        self._monitoring = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_loop,
            args=(callback, region, detect_changes),
            daemon=True,
        )
        self._monitor_thread.start()
        log.info("Screen monitoring started at %.1f FPS", self.fps)

    def stop_monitoring(self) -> None:
        """Stop the background capture loop."""
        self._monitoring = False
        if self._monitor_thread:
            self._monitor_thread.join(timeout=3)
        log.info("Screen monitoring stopped.")

    @property
    def is_monitoring(self) -> bool:
        """Return True if continuous monitoring is active."""
        return self._monitoring

    # ─── Frame Differencing ───────────────────────────────────────────────

    def frames_differ(
        self,
        frame_a: np.ndarray,
        frame_b: np.ndarray,
    ) -> bool:
        """
        Return True if the two frames differ significantly.

        Args:
            frame_a: Previous frame.
            frame_b: Current frame.

        Returns:
            bool
        """
        if frame_a.shape != frame_b.shape:
            return True
        diff = np.abs(frame_a.astype(np.int16) - frame_b.astype(np.int16))
        return float(diff.mean()) > self._change_threshold

    # ─── Internal ─────────────────────────────────────────────────────────

    def _monitor_loop(
        self,
        callback: Callable[[np.ndarray], None],
        region: Optional[Tuple[int, int, int, int]],
        detect_changes: bool,
    ) -> None:
        """Background capture loop."""
        interval = 1.0 / max(self.fps, 0.1)
        while self._monitoring:
            start = time.monotonic()
            frame = self.capture(region=region, as_numpy=True)
            if frame is not None:
                should_call = True
                if detect_changes and self._last_frame is not None:
                    should_call = self.frames_differ(self._last_frame, frame)
                if should_call:
                    self._last_frame = frame
                    try:
                        callback(frame)
                    except Exception as exc:  # noqa: BLE001
                        log.debug("Capture callback error: %s", exc)
            elapsed = time.monotonic() - start
            sleep_time = interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    @staticmethod
    def _get_monitor(
        sct: "mss.MSSBase",
        region: Optional[Tuple[int, int, int, int]],
    ) -> dict:
        """Build the mss monitor dict from region or use monitor 1."""
        if region:
            left, top, width, height = region
            return {"left": left, "top": top, "width": width, "height": height}
        return sct.monitors[1]  # Primary monitor
