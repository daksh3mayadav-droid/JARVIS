"""
voice/voice_corrector.py — Vosk transcription correction for JARVIS

Applies a dictionary of known Vosk mishearings and fuzzy matching to clean
up speech-to-text output before it reaches the intent classifier.

The small Vosk model often produces phonetically similar but incorrect
transcriptions.  This module corrects the most common mistakes so that
JARVIS understands commands like "open YouTube" even when Vosk hears
"visit the feet you".
"""

from __future__ import annotations

import re
from typing import Optional

from utils.logger import get_logger

log = get_logger("voice.corrector")

# ─── Static correction table ─────────────────────────────────────────────────
# Maps known Vosk mishearings → correct text.
# Keys are matched as substrings (longest match first to avoid partial
# replacements shadowing longer ones).

VOICE_CORRECTIONS: dict[str, str] = {
    # CPU / processor
    "cp you use age":       "cpu usage",
    "cp you":               "cpu",
    "see pee you":          "cpu",
    "believes it":          "cpu usage",
    "use age":              "usage",

    # YouTube
    "please it is you go":  "please open youtube",
    "it is you go video":   "youtube video",
    "the feet you":         "youtube",
    "is you go video":      "youtube video",
    "feet you":             "youtube",
    "it is you go":         "youtube",
    "you go video":         "youtube video",
    "you go":               "youtube",
    "you to":               "youtube",

    # Filler / noise tokens
    "visit the":            "",
    "resume though the":    "resume the",
    "resume though":        "resume",
    "though the":           "the",

    # Common verbs
}

# ─── Phonetic keyword map ─────────────────────────────────────────────────────
# Maps common mishearings of critical keywords to the correct keyword.
# These are checked against individual words in the transcription.

PHONETIC_KEYWORDS: dict[str, str] = {
    # youtube
    "utube":    "youtube",
    "u-tube":   "youtube",
    "youtub":   "youtube",
    "youtubb":  "youtube",
    "youtoob":  "youtube",

    # chrome
    "crome":    "chrome",
    "kromb":    "chrome",
    "chrom":    "chrome",

    # firefox
    "firfox":   "firefox",
    "firefocks": "firefox",

    # steam
    "steem":    "steam",

    # screenshot
    "sceenshot":    "screenshot",
    "screenshoot":  "screenshot",
    "screnshoot":   "screenshot",

    # battery
    "batery":   "battery",
    "batry":    "battery",

    # bluetooth
    "bluethooth": "bluetooth",
    "bluetooh":   "bluetooth",

    # brightness
    "brightnes":  "brightness",
    "brtness":    "brightness",

    # volume
    "volum":    "volume",
    "vollume":  "volume",
}

# ─── Fuzzy matching ───────────────────────────────────────────────────────────

# Critical command words that are worth fuzzy-matching (short enough that
# thefuzz can find near-misses cheaply).
FUZZY_KEYWORDS = [
    "youtube", "chrome", "firefox", "steam", "screenshot",
    "battery", "bluetooth", "brightness", "volume",
    "cpu", "gpu", "ram", "wifi", "settings",
    "pause", "resume", "play", "mute", "fullscreen",
]

try:
    from thefuzz import fuzz as _fuzz
    _THEFUZZ_AVAILABLE = True
except ImportError:
    _THEFUZZ_AVAILABLE = False
    log.debug("thefuzz not installed — fuzzy matching disabled.")


def _fuzzy_fix_word(word: str, threshold: int = 85) -> str:
    """
    Return the closest FUZZY_KEYWORDS entry if it scores above *threshold*.

    Args:
        word: A single (lower-case) word from the transcription.
        threshold: Minimum ratio score (0–100) required for a replacement.

    Returns:
        The corrected keyword or the original word if no match found.
    """
    if not _THEFUZZ_AVAILABLE or len(word) < 3:
        return word

    best_score = 0
    best_match = word
    for kw in FUZZY_KEYWORDS:
        score = _fuzz.ratio(word, kw)
        if score > best_score:
            best_score = score
            best_match = kw

    if best_score >= threshold:
        if best_match != word:
            log.debug("Fuzzy fix: '%s' → '%s' (score=%d)", word, best_match, best_score)
        return best_match
    return word


# ─── Public API ───────────────────────────────────────────────────────────────

class VoiceCorrector:
    """
    Corrects Vosk speech-to-text output using a combination of:

    1. Static substring replacements (VOICE_CORRECTIONS)
    2. Phonetic keyword lookups (PHONETIC_KEYWORDS)
    3. Fuzzy string matching via thefuzz (when available)
    """

    def correct(self, text: str) -> str:
        """
        Apply all correction passes to *text* and return the cleaned string.

        Args:
            text: Raw transcription from Vosk (lower-cased or mixed case).

        Returns:
            Corrected, lower-cased text suitable for intent classification.
        """
        if not text:
            return text

        corrected = text.lower().strip()
        corrected = self._apply_static_corrections(corrected)
        corrected = self._apply_phonetic_keywords(corrected)
        corrected = self._apply_fuzzy_corrections(corrected)

        # Collapse any extra whitespace that may result from removals
        corrected = re.sub(r"\s{2,}", " ", corrected).strip()

        if corrected != text.lower().strip():
            log.info("Voice corrected: '%s' → '%s'", text, corrected)

        return corrected

    # ─── Internal passes ──────────────────────────────────────────────────

    def _apply_static_corrections(self, text: str) -> str:
        """Apply the VOICE_CORRECTIONS dictionary (longest key first)."""
        # Sort by length descending so longer patterns take precedence
        for bad, good in sorted(VOICE_CORRECTIONS.items(), key=lambda x: -len(x[0])):
            if bad in text:
                text = text.replace(bad, good)
        return text

    def _apply_phonetic_keywords(self, text: str) -> str:
        """Replace individual words that match PHONETIC_KEYWORDS."""
        words = text.split()
        fixed = [PHONETIC_KEYWORDS.get(w, w) for w in words]
        return " ".join(fixed)

    def _apply_fuzzy_corrections(self, text: str) -> str:
        """Apply per-word fuzzy matching to catch remaining mishearings."""
        if not _THEFUZZ_AVAILABLE:
            return text
        words = text.split()
        fixed = [_fuzzy_fix_word(w) for w in words]
        return " ".join(fixed)


# Module-level singleton for convenient import
_corrector: Optional[VoiceCorrector] = None


def get_corrector() -> VoiceCorrector:
    """Return the shared VoiceCorrector singleton."""
    global _corrector  # noqa: PLW0603
    if _corrector is None:
        _corrector = VoiceCorrector()
    return _corrector


def correct_voice_input(text: str) -> str:
    """
    Convenience wrapper: correct *text* using the shared VoiceCorrector.

    Args:
        text: Raw Vosk transcription.

    Returns:
        Corrected text.
    """
    return get_corrector().correct(text)
