"""
core/safety.py — Safety classifier for JARVIS actions

Three risk levels: SAFE (auto-execute), RISKY (single confirm),
DANGEROUS (double confirm with timeout).
"""

from __future__ import annotations

import time
from enum import Enum
from typing import Optional

from utils.logger import get_logger
from utils.tars_personality import TARSPersonality

log = get_logger("safety")


class RiskLevel(Enum):
    """Risk classification for JARVIS actions."""

    SAFE = "SAFE"
    RISKY = "RISKY"
    DANGEROUS = "DANGEROUS"


# ─── Classification Rules ─────────────────────────────────────────────────────

# Keywords that indicate the action type
_DANGEROUS_KEYWORDS = (
    "delete", "remove", "uninstall", "format", "wipe",
    "kill process", "terminate", "registry edit", "regedit",
    "rm -rf", "del /f", "permanent", "overwrite system",
    "disable defender", "firewall off", "netsh",
)

_RISKY_KEYWORDS = (
    "move", "rename", "copy to system", "modify", "edit config",
    "change settings", "restart", "shutdown", "log off",
    "install", "execute", "run script", "powershell", "cmd",
    "elevated", "admin", "sudo",
)

_SAFE_KEYWORDS = (
    "open", "launch", "show", "display", "list", "search",
    "read", "view", "screenshot", "info", "status", "help",
    "volume", "brightness", "scroll", "click", "type",
    "switch window", "minimize", "maximize",
    # YouTube actions (all yt_* are read-only keyboard shortcuts)
    "yt_", "play_youtube", "youtube_search",
    # System information queries (read-only)
    "get_cpu", "get_ram", "get_gpu", "get_battery", "get_system_info",
    # Browser / navigation
    "google_search", "open_url",
    # Settings toggles (non-destructive)
    "toggle_wifi", "toggle_bluetooth", "set_volume", "set_brightness",
    # App control
    "open_app",
    # Mouse control
    "click", "right_click", "double_click", "scroll_up", "scroll_down",
    "mouse_click",
    # Window control
    "minimize_window", "maximize_window", "close_window", "switch_window",
    "snap_left", "snap_right", "show_desktop", "task_view",
    # Browser tab control
    "new_tab", "close_tab", "next_tab", "prev_tab", "refresh_page",
    "go_back", "go_forward",
)


class SafetyClassifier:
    """
    Classifies actions into SAFE / RISKY / DANGEROUS.

    Provides confirmation prompts with configurable timeouts,
    and maintains an audit log of executed actions.
    """

    def __init__(
        self,
        safe_mode: bool = True,
        personality: Optional[TARSPersonality] = None,
    ) -> None:
        """
        Initialize the safety classifier.

        Args:
            safe_mode: When False, RISKY actions auto-execute without
                       confirmation (DANGEROUS still requires it).
            personality: TARSPersonality instance for prompt formatting.
        """
        self.safe_mode = safe_mode
        self.personality = personality or TARSPersonality()
        self._audit_log: list[dict] = []

    # ─── Classification ───────────────────────────────────────────────────

    def classify(self, action: str) -> RiskLevel:
        """
        Determine the risk level of an action string.

        Args:
            action: Human-readable description of the action.

        Returns:
            :class:`RiskLevel` enum value.
        """
        action_lower = action.lower()

        # Dangerous takes precedence
        for kw in _DANGEROUS_KEYWORDS:
            if kw in action_lower:
                log.debug("Action classified DANGEROUS: %s", action)
                return RiskLevel.DANGEROUS

        for kw in _RISKY_KEYWORDS:
            if kw in action_lower:
                log.debug("Action classified RISKY: %s", action)
                return RiskLevel.RISKY

        for kw in _SAFE_KEYWORDS:
            if kw in action_lower:
                log.debug("Action classified SAFE: %s", action)
                return RiskLevel.SAFE

        # Default: treat unknown as RISKY
        log.debug("Action defaulting to RISKY: %s", action)
        return RiskLevel.RISKY

    # ─── Confirmation ─────────────────────────────────────────────────────

    def request_confirmation(
        self,
        action: str,
        level: Optional[RiskLevel] = None,
        timeout: float = 30.0,
    ) -> bool:
        """
        Ask the user to confirm a risky or dangerous action.

        Args:
            action: Action description to display.
            level: Risk level (classified automatically if None).
            timeout: Seconds to wait before auto-cancelling (0 = no timeout).

        Returns:
            True if the user confirmed, False if denied or timed out.
        """
        if level is None:
            level = self.classify(action)

        if level == RiskLevel.SAFE:
            return True
        if level == RiskLevel.RISKY and not self.safe_mode:
            return True

        prompt = self._build_prompt(action, level)
        print(f"\n⚠️  {prompt}")

        if level == RiskLevel.DANGEROUS:
            print("  ⛔  This is a DANGEROUS action. Type 'YES I AM SURE' to confirm.")
            expected = "YES I AM SURE"
        else:
            print("  ⚠️   Type 'yes' to confirm or anything else to cancel.")
            expected = "yes"

        if timeout > 0:
            print(f"  ⏱️   Auto-cancelling in {int(timeout)} seconds...")

        start = time.time()
        try:
            response = input("  Confirm: ").strip()
        except (EOFError, KeyboardInterrupt):
            response = ""

        elapsed = time.time() - start
        if timeout > 0 and elapsed >= timeout:
            print("  ⏱️  Timeout — action cancelled.")
            self._log_action(action, level, confirmed=False, reason="timeout")
            return False

        confirmed = response == expected
        self._log_action(action, level, confirmed=confirmed, reason="user_input")

        if confirmed:
            log.info("User confirmed %s action: %s", level.value, action)
        else:
            log.info("User denied %s action: %s", level.value, action)
            print("  ❌  Action cancelled.")

        return confirmed

    def is_safe_to_auto_execute(self, action: str) -> bool:
        """
        Return True if the action can be executed without confirmation.

        Args:
            action: Action description.

        Returns:
            bool
        """
        level = self.classify(action)
        if level == RiskLevel.SAFE:
            return True
        if level == RiskLevel.RISKY and not self.safe_mode:
            return True
        return False

    # ─── Audit Log ────────────────────────────────────────────────────────

    def _log_action(
        self,
        action: str,
        level: RiskLevel,
        confirmed: bool,
        reason: str,
    ) -> None:
        """Append an action to the in-memory audit trail."""
        entry = {
            "action": action,
            "level": level.value,
            "confirmed": confirmed,
            "reason": reason,
            "timestamp": time.time(),
        }
        self._audit_log.append(entry)
        log.info(
            "AUDIT | level=%s confirmed=%s reason=%s | %s",
            level.value,
            confirmed,
            reason,
            action,
        )

    def get_audit_log(self) -> list[dict]:
        """Return the full audit log."""
        return list(self._audit_log)

    def clear_audit_log(self) -> None:
        """Clear the in-memory audit log."""
        self._audit_log.clear()

    # ─── Helpers ──────────────────────────────────────────────────────────

    def _build_prompt(self, action: str, level: RiskLevel) -> str:
        """Build the confirmation prompt string."""
        if level == RiskLevel.DANGEROUS:
            return f"DANGEROUS ACTION: {action}"
        return f"RISKY ACTION: {action}"
