"""
vision/ocr_engine.py — OCR engine for JARVIS

Primary: EasyOCR (GPU-accelerated on GTX 1650)
Fallback: pytesseract if EasyOCR unavailable
"""

from __future__ import annotations

import hashlib
import time
from pathlib import Path
from typing import Any, Optional

import numpy as np

try:
    import easyocr
    EASYOCR_AVAILABLE = True
except ImportError:
    EASYOCR_AVAILABLE = False

try:
    import pytesseract
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False

try:
    from PIL import Image
    PIL_AVAILABLE = True
except ImportError:
    PIL_AVAILABLE = False

from utils.helpers import get_config
from utils.logger import get_logger

log = get_logger("vision.ocr")

# ─── Cache ────────────────────────────────────────────────────────────────────

_OCR_CACHE: dict[str, tuple[float, list]] = {}  # hash → (timestamp, results)
_CACHE_TTL = 5.0   # seconds


def _image_hash(image: np.ndarray) -> str:
    """Compute a fast hash of the image for caching."""
    small = image[::8, ::8].tobytes()  # Downsample for speed
    return hashlib.md5(small).hexdigest()  # noqa: S324


class OCREngine:
    """
    OCR engine with EasyOCR primary and pytesseract fallback.

    Extracts text with bounding boxes and confidence scores.
    GPU acceleration used when available (GTX 1650).
    """

    def __init__(self) -> None:
        """Initialize the OCR engine."""
        config = get_config()
        vision_cfg = config.get("vision", {})

        self._engine_pref = vision_cfg.get("ocr_engine", "easyocr")
        self._reader: Optional[Any] = None
        self._gpu_available = self._check_gpu()

        log.info(
            "OCR engine init. Preferred: %s | GPU: %s | EasyOCR: %s | Tesseract: %s",
            self._engine_pref,
            self._gpu_available,
            EASYOCR_AVAILABLE,
            TESSERACT_AVAILABLE,
        )

    def _check_gpu(self) -> bool:
        """Return True if CUDA is available."""
        try:
            import torch
            return torch.cuda.is_available()
        except ImportError:
            return False

    def _get_reader(self) -> Optional[Any]:
        """Lazy-initialize EasyOCR reader."""
        if self._reader is not None:
            return self._reader
        if not EASYOCR_AVAILABLE:
            return None
        try:
            log.info("Initializing EasyOCR reader (GPU=%s)…", self._gpu_available)
            self._reader = easyocr.Reader(["en"], gpu=self._gpu_available, verbose=False)
            log.info("EasyOCR ready.")
            return self._reader
        except Exception as exc:  # noqa: BLE001
            log.error("EasyOCR init failed: %s", exc)
            return None

    # ─── Public API ───────────────────────────────────────────────────────

    def extract_text(
        self,
        image: "np.ndarray | Image.Image | Path | str",
        use_cache: bool = True,
    ) -> str:
        """
        Extract all visible text from an image.

        Args:
            image: numpy array, PIL Image, or path to image file.
            use_cache: Whether to use the recent-result cache.

        Returns:
            Concatenated text string.
        """
        results = self.extract_with_boxes(image, use_cache=use_cache)
        return " ".join(r["text"] for r in results if r["text"].strip())

    def extract_with_boxes(
        self,
        image: "np.ndarray | Image.Image | Path | str",
        use_cache: bool = True,
    ) -> list[dict]:
        """
        Extract text with bounding boxes and confidence scores.

        Args:
            image: Input image.
            use_cache: Cache recent results by image hash.

        Returns:
            List of dicts with keys: text, bbox, confidence.
            bbox format: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
        """
        arr = self._to_numpy(image)
        if arr is None:
            return []

        # Cache lookup
        img_hash = _image_hash(arr) if use_cache else ""
        if use_cache and img_hash in _OCR_CACHE:
            ts, cached = _OCR_CACHE[img_hash]
            if time.time() - ts < _CACHE_TTL:
                return cached

        results = self._run_ocr(arr)

        if use_cache and img_hash:
            _OCR_CACHE[img_hash] = (time.time(), results)

        return results

    def batch_extract(self, images: list) -> list[str]:
        """
        Extract text from multiple images.

        Args:
            images: List of images (numpy arrays, PIL Images, or paths).

        Returns:
            List of text strings corresponding to each image.
        """
        return [self.extract_text(img, use_cache=False) for img in images]

    # ─── Internal ─────────────────────────────────────────────────────────

    def _run_ocr(self, arr: np.ndarray) -> list[dict]:
        """
        Dispatch to the appropriate OCR backend.

        Args:
            arr: numpy array (H, W, 3) in RGB.

        Returns:
            List of text+bbox+confidence dicts.
        """
        # Try preferred engine first
        if self._engine_pref == "easyocr" and EASYOCR_AVAILABLE:
            results = self._easyocr_extract(arr)
            if results:
                return results

        if TESSERACT_AVAILABLE:
            return self._tesseract_extract(arr)

        if EASYOCR_AVAILABLE:
            return self._easyocr_extract(arr)

        log.warning("No OCR backend available. Returning empty results.")
        return []

    def _easyocr_extract(self, arr: np.ndarray) -> list[dict]:
        """Run EasyOCR on the image."""
        reader = self._get_reader()
        if not reader:
            return []
        try:
            raw = reader.readtext(arr)
            results = []
            for item in raw:
                bbox, text, conf = item
                results.append({"text": text, "bbox": bbox, "confidence": float(conf)})
            return results
        except Exception as exc:  # noqa: BLE001
            log.error("EasyOCR failed: %s", exc)
            return []

    def _tesseract_extract(self, arr: np.ndarray) -> list[dict]:
        """Run pytesseract on the image."""
        try:
            if PIL_AVAILABLE:
                img = Image.fromarray(arr)
            else:
                log.warning("Pillow required for pytesseract mode.")
                return []

            data = pytesseract.image_to_data(
                img,
                output_type=pytesseract.Output.DICT,
                config="--psm 11",
            )
            results = []
            for i, text in enumerate(data["text"]):
                if not text.strip():
                    continue
                conf = float(data["conf"][i])
                if conf < 0:
                    continue
                x, y, w, h = (
                    data["left"][i], data["top"][i],
                    data["width"][i], data["height"][i],
                )
                bbox = [[x, y], [x + w, y], [x + w, y + h], [x, y + h]]
                results.append({
                    "text": text,
                    "bbox": bbox,
                    "confidence": conf / 100.0,
                })
            return results
        except Exception as exc:  # noqa: BLE001
            log.error("Tesseract failed: %s", exc)
            return []

    @staticmethod
    def _to_numpy(
        image: "np.ndarray | Image.Image | Path | str",
    ) -> Optional[np.ndarray]:
        """Convert image to numpy array (H, W, 3) RGB."""
        if isinstance(image, np.ndarray):
            # Handle BGRA from mss
            if image.ndim == 3 and image.shape[2] == 4:
                return image[:, :, :3][..., ::-1]
            return image

        if PIL_AVAILABLE and isinstance(image, Image.Image):
            return np.array(image.convert("RGB"))

        if isinstance(image, (Path, str)):
            if PIL_AVAILABLE:
                try:
                    return np.array(Image.open(str(image)).convert("RGB"))
                except Exception as exc:  # noqa: BLE001
                    log.error("Failed to load image from path: %s", exc)
            return None

        log.warning("Unknown image type: %s", type(image))
        return None
