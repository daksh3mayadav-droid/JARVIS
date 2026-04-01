"""
utils/tars_personality.py — TARS Personality Engine for JARVIS

Transforms plain responses into TARS-style (Interstellar) dialogue.
Humor level 0-100: 0 = purely factual, 100 = maximum wit.
"""

from __future__ import annotations

import random
import re
from typing import Optional

from utils.logger import get_logger

log = get_logger("tars_personality")

# ─── Response Pools ───────────────────────────────────────────────────────────

ACKNOWLEDGMENTS = [
    "Done.",
    "On it.",
    "Consider it handled.",
    "Executing.",
    "Already on it.",
    "Right away.",
    "Understood.",
    "As you wish.",
    "Working on it.",
]

COMPLETIONS = [
    "Task complete.",
    "Done. Anything else?",
    "Finished. That's all there is to it.",
    "Complete. You're welcome.",
    "Mission accomplished. Mostly.",
]

ERROR_PREFIXES = [
    "Well, that didn't go as planned.",
    "Slight technical hiccup.",
    "Something went sideways.",
    "Encountered a problem.",
    "That failed. Surprising? Not really.",
]

ERROR_SUFFIXES_HUMOR = [
    "My fault. Or yours. Let's say neither.",
    "Humor setting too high for this error.",
    "I'd blame the hardware, but that feels dishonest.",
    "On the bright side, at least it failed quickly.",
    "This is fine. Everything is fine.",
]

FILE_OPS_HUMOR = [
    "Moving files. Try not to hoard so many PDFs next time.",
    "Organizing your digital chaos. You're welcome.",
    "Found it. It was exactly where you didn't look.",
    "Deleted. It's gone. Forever. You're sure about that, right?",
    "Creating folder. Because apparently one more folder helps.",
]

APP_LAUNCH_HUMOR = [
    "Opening Chrome. I'll pretend not to notice the 47 tabs.",
    "Launching. Fingers crossed the app cooperates.",
    "Starting it up. This always takes longer than it should.",
    "On it. Hope it doesn't decide to update first.",
    "Opening. You've used this one before. A lot.",
]

SYSTEM_INFO_HUMOR = [
    "Your CPU is running at {value}%. Might want to close something. Or not. I'm just an AI.",
    "RAM at {value}%. Comfortable. For now.",
    "GPU temperature: {value}°C. Still within acceptable parameters. Barely.",
    "Battery at {value}%. You might want to think about a charger.",
    "Everything checks out. Relatively speaking.",
]

THINKING_PHRASES = [
    "Analyzing...",
    "Processing...",
    "Let me think about that.",
    "One moment.",
    "Computing.",
    "Working on it.",
]

SEARCH_PHRASES = [
    "Scanning...",
    "Looking for it.",
    "Searching your system.",
    "Let me find that for you.",
]

NOT_FOUND_PHRASES = [
    "Nothing found. Maybe try a different approach.",
    "Can't locate that. It may not exist.",
    "I looked. It's not there.",
    "Not found. I'm thorough, so I mean it.",
]

PLANNING_PHRASES = [
    "Planning the approach.",
    "Mapping out the steps.",
    "Formulating a plan. Give me a moment.",
    "Breaking this down into manageable pieces.",
]

SAFETY_WARNINGS = [
    "This action is irreversible. Confirm?",
    "That's a destructive operation. Are you sure?",
    "This could cause problems if done wrong. Proceed?",
    "High-risk action detected. Explicit confirmation required.",
]

# ─── Context-aware humor additions ────────────────────────────────────────────

CONTEXT_HUMOR: dict[str, list[str]] = {
    "file_delete": [
        "Sending to the digital void.",
        "Gone. No ceremony, no burial.",
        "Deleted. Probably fine.",
    ],
    "file_move": [
        "Moving it. Don't ask me to move it back.",
        "Relocating. Very exciting.",
    ],
    "app_open": [
        "Here we go again.",
        "Opening. For the {n}th time today.",
    ],
    "system_stats": [
        "Your machine is technically alive.",
        "System nominal. Ish.",
    ],
    "search": [
        "Checking everywhere. Except there. Oh wait, yes there too.",
        "Systematic search initiated.",
    ],
    "settings": [
        "Navigating the labyrinth known as Windows Settings.",
        "Settings. Where good intentions go to die.",
    ],
    "browser": [
        "Opening the internet. Please contain your enthusiasm.",
        "Launching browser. Please limit yourself to one search this time.",
    ],
    "error": [
        "Well. That happened.",
        "I'll add that to my list of surprises.",
    ],
}


# ─── Main Class ───────────────────────────────────────────────────────────────

class TARSPersonality:
    """
    TARS personality filter.

    Transforms plain text responses into TARS-style dialogue.
    Humor is adjustable from 0 (factual) to 100 (maximum wit).
    """

    def __init__(self, humor_level: int = 75) -> None:
        """
        Initialize the TARS personality engine.

        Args:
            humor_level: Integer 0-100. Controls how often witty
                         remarks are appended to responses.
        """
        self.humor_level = max(0, min(100, humor_level))
        log.debug("TARS personality initialized. Humor: %d%%", self.humor_level)

    # ─── Public API ───────────────────────────────────────────────────────

    def respond(
        self,
        text: str,
        context: Optional[str] = None,
        serious: bool = False,
    ) -> str:
        """
        Apply TARS personality to a response string.

        Args:
            text: The plain response text.
            context: Optional context hint (e.g. 'file_delete', 'app_open').
            serious: If True, suppress all humor regardless of humor_level.

        Returns:
            TARS-styled response string.
        """
        if not text:
            return text

        result = self._clean(text)

        if not serious and self._roll():
            result = self._inject_humor(result, context)

        return result

    def acknowledge(self, task: str = "") -> str:
        """
        Return a TARS acknowledgment for starting a task.

        Args:
            task: Short description of the task being started.

        Returns:
            Acknowledgment string.
        """
        ack = random.choice(ACKNOWLEDGMENTS)
        if task and self._roll(threshold=40):
            return f"{ack} {task}."
        return ack

    def complete(self, extra: str = "") -> str:
        """
        Return a TARS task-completion phrase.

        Args:
            extra: Optional extra info to append.

        Returns:
            Completion phrase.
        """
        phrase = random.choice(COMPLETIONS)
        if extra:
            return f"{phrase} {extra}"
        return phrase

    def error(self, reason: str, serious: bool = False) -> str:
        """
        Return a TARS-style error message.

        Args:
            reason: Human-readable description of the error.
            serious: If True, omit humor suffix.

        Returns:
            Error message string.
        """
        prefix = random.choice(ERROR_PREFIXES)
        msg = f"{prefix} {reason}"
        if not serious and self._roll(threshold=50):
            suffix = random.choice(ERROR_SUFFIXES_HUMOR)
            msg = f"{msg} {suffix}"
        return msg

    def thinking(self) -> str:
        """Return a thinking/processing phrase."""
        return random.choice(THINKING_PHRASES)

    def planning(self) -> str:
        """Return a planning phrase."""
        return random.choice(PLANNING_PHRASES)

    def not_found(self, item: str = "") -> str:
        """Return a not-found response."""
        phrase = random.choice(NOT_FOUND_PHRASES)
        if item:
            return f"{item}: {phrase.lower()}"
        return phrase

    def safety_warning(self) -> str:
        """Return a safety confirmation prompt."""
        return random.choice(SAFETY_WARNINGS)

    def file_op(self, operation: str = "") -> str:
        """Return a file-operation comment."""
        if self._roll(threshold=60):
            humor = random.choice(FILE_OPS_HUMOR)
            if operation:
                return f"{operation}. {humor}"
            return humor
        return operation or random.choice(ACKNOWLEDGMENTS)

    def app_launch(self, app_name: str = "") -> str:
        """Return an app-launch comment."""
        humor = random.choice(APP_LAUNCH_HUMOR)
        if app_name:
            # Replace generic "Chrome" reference with actual app name
            humor = re.sub(r"Chrome|the app", app_name, humor, count=1)
            return humor
        return random.choice(ACKNOWLEDGMENTS)

    def system_info(self, metric: str = "", value: str = "") -> str:
        """Return a system-info comment with optional metric injection."""
        template = random.choice(SYSTEM_INFO_HUMOR)
        return template.format(value=value, metric=metric)

    def set_humor(self, level: int) -> None:
        """Dynamically update humor level."""
        self.humor_level = max(0, min(100, level))
        log.info("Humor level updated to %d%%", self.humor_level)

    # ─── Internal ─────────────────────────────────────────────────────────

    def _roll(self, threshold: Optional[int] = None) -> bool:
        """
        Return True if a random roll falls within humor_level.

        Args:
            threshold: Custom threshold override (0-100).

        Returns:
            bool
        """
        limit = threshold if threshold is not None else self.humor_level
        return random.randint(1, 100) <= limit

    def _clean(self, text: str) -> str:
        """Normalize whitespace and capitalization."""
        text = text.strip()
        if text and not text[0].isupper():
            text = text[0].upper() + text[1:]
        # Collapse multiple spaces/newlines
        text = re.sub(r"\s{2,}", " ", text)
        return text

    def _inject_humor(self, text: str, context: Optional[str]) -> str:
        """
        Append a context-appropriate humorous remark if available.

        Args:
            text: Base text.
            context: Context key for CONTEXT_HUMOR lookup.

        Returns:
            Possibly augmented text.
        """
        if context and context in CONTEXT_HUMOR:
            remark = random.choice(CONTEXT_HUMOR[context])
            # Fill placeholders
            remark = remark.replace("{n}", str(random.randint(3, 20)))
            return f"{text} {remark}"
        return text
