"""
automation/task_automator.py — Automation engine for JARVIS

Record/replay action sequences, scheduled tasks,
trigger-based automations, and workflow templates.
"""

from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Callable, Optional

from utils.helpers import get_config
from utils.logger import get_logger

log = get_logger("automation.task_automator")

# ─── Data Classes ─────────────────────────────────────────────────────────────


@dataclass
class RecordedAction:
    """A single recorded mouse/keyboard action."""

    action_type: str    # click, move, type, hotkey, scroll, wait
    timestamp: float
    data: dict          # Action-specific payload


@dataclass
class Automation:
    """A named, saveable automation script."""

    name: str
    description: str = ""
    actions: list[RecordedAction] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    playback_speed: float = 1.0   # Multiplier for timing

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "actions": [asdict(a) for a in self.actions],
            "created_at": self.created_at,
            "playback_speed": self.playback_speed,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Automation":
        actions = [
            RecordedAction(**a) for a in data.get("actions", [])
        ]
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            actions=actions,
            created_at=data.get("created_at", time.time()),
            playback_speed=data.get("playback_speed", 1.0),
        )


# ─── Scheduled Task ───────────────────────────────────────────────────────────


@dataclass
class ScheduledTask:
    """A task scheduled to run at a specific time or interval."""

    name: str
    func: Callable
    interval_seconds: Optional[float] = None    # Recurring interval
    run_at: Optional[float] = None              # One-time Unix timestamp
    enabled: bool = True
    last_run: Optional[float] = None
    run_count: int = 0


class TaskAutomator:
    """
    Automation engine for JARVIS.

    Features:
    - Record mouse/keyboard action sequences
    - Replay recordings with configurable speed
    - Schedule tasks (one-time or recurring)
    - Trigger-based automations (folder watcher, etc.)
    - Pre-built workflow templates
    - Save/load automations as JSON
    """

    def __init__(self) -> None:
        """Initialize the task automator."""
        config = get_config()
        auto_cfg = config.get("automation", {})
        self._scripts_dir = Path(auto_cfg.get("scripts_dir", "data/automations"))
        self._scripts_dir.mkdir(parents=True, exist_ok=True)

        self._automations: dict[str, Automation] = {}
        self._scheduled: list[ScheduledTask] = []
        self._recording: Optional[Automation] = None
        self._is_recording = False

        self._scheduler_thread: Optional[threading.Thread] = None
        self._scheduler_running = False

        self._controller = None  # Injected: SystemController
        log.info("TaskAutomator initialized. Scripts dir: %s", self._scripts_dir)

    def set_controller(self, controller) -> None:
        """Inject a SystemController for action replay."""
        self._controller = controller

    # ─── Recording ────────────────────────────────────────────────────────

    def start_recording(self, name: str, description: str = "") -> None:
        """
        Begin recording an action sequence.

        Args:
            name: Name for this automation.
            description: Optional description.
        """
        self._recording = Automation(name=name, description=description)
        self._is_recording = True
        log.info("Recording started: '%s'", name)

    def stop_recording(self) -> Optional[Automation]:
        """
        Stop recording and save the automation.

        Returns:
            The completed Automation or None.
        """
        if not self._is_recording or not self._recording:
            log.warning("No active recording to stop.")
            return None

        self._is_recording = False
        automation = self._recording
        self._recording = None
        self._automations[automation.name] = automation
        self.save_automation(automation)
        log.info("Recording stopped: '%s' (%d actions)", automation.name, len(automation.actions))
        return automation

    def record_action(self, action_type: str, **data: Any) -> None:
        """
        Record a single action (called by SystemController hooks).

        Args:
            action_type: Type of action (click, type, hotkey, etc.).
            **data: Action-specific keyword arguments.
        """
        if not self._is_recording or not self._recording:
            return
        action = RecordedAction(
            action_type=action_type,
            timestamp=time.time(),
            data=data,
        )
        self._recording.actions.append(action)

    # ─── Playback ─────────────────────────────────────────────────────────

    def play(
        self,
        name: str,
        speed_multiplier: float = 1.0,
        loop: bool = False,
        loop_count: int = 1,
    ) -> bool:
        """
        Replay a recorded automation.

        Args:
            name: Automation name.
            speed_multiplier: Playback speed (1.0 = original, 2.0 = 2× faster).
            loop: If True, repeat playback.
            loop_count: Number of repetitions (0 = infinite).

        Returns:
            True if automation was found and started.
        """
        automation = self._automations.get(name) or self._load_automation(name)
        if not automation:
            log.warning("Automation not found: '%s'", name)
            return False

        def _run():
            iterations = 0
            while True:
                self._replay_automation(automation, speed_multiplier)
                iterations += 1
                if not loop or (loop_count > 0 and iterations >= loop_count):
                    break

        threading.Thread(target=_run, daemon=True).start()
        return True

    def _replay_automation(
        self,
        automation: Automation,
        speed_multiplier: float = 1.0,
    ) -> None:
        """Execute all actions in an automation."""
        if not self._controller:
            log.warning("No controller set. Cannot replay automation.")
            return

        log.info("Replaying '%s' (%d actions)", automation.name, len(automation.actions))
        prev_ts = None

        for action in automation.actions:
            # Honour timing between actions
            if prev_ts is not None:
                delay = (action.timestamp - prev_ts) / speed_multiplier
                if 0 < delay < 5.0:  # Cap individual delays at 5s
                    time.sleep(delay)
            prev_ts = action.timestamp

            try:
                self._execute_recorded_action(action)
            except Exception as exc:  # noqa: BLE001
                log.error("Replay action failed: %s", exc)

    def _execute_recorded_action(self, action: RecordedAction) -> None:
        """Execute a single recorded action via the controller."""
        c = self._controller
        d = action.data
        t = action.action_type

        if t == "click":
            c.click(d.get("x"), d.get("y"), d.get("button", "left"))
        elif t == "move":
            c.move(d.get("x", 0), d.get("y", 0))
        elif t == "type":
            c.type_text(d.get("text", ""), human_speed=False)
        elif t == "hotkey":
            c.hotkey(*d.get("keys", []))
        elif t == "press_key":
            c.press_key(d.get("key", ""))
        elif t == "scroll":
            c.scroll(d.get("clicks", 0))
        elif t == "wait":
            time.sleep(d.get("seconds", 0))

    # ─── Scheduling ───────────────────────────────────────────────────────

    def schedule(
        self,
        name: str,
        func: Callable,
        interval_seconds: Optional[float] = None,
        run_at: Optional[float] = None,
    ) -> None:
        """
        Schedule a function to run at an interval or specific time.

        Args:
            name: Task name.
            func: Callable to execute.
            interval_seconds: Recurring interval in seconds.
            run_at: One-time Unix timestamp.
        """
        task = ScheduledTask(
            name=name,
            func=func,
            interval_seconds=interval_seconds,
            run_at=run_at,
        )
        self._scheduled.append(task)
        log.info("Scheduled task: '%s' (interval=%s, at=%s)", name, interval_seconds, run_at)

        if not self._scheduler_running:
            self._start_scheduler()

    def unschedule(self, name: str) -> bool:
        """Remove a scheduled task by name."""
        before = len(self._scheduled)
        self._scheduled = [t for t in self._scheduled if t.name != name]
        return len(self._scheduled) < before

    def _start_scheduler(self) -> None:
        """Start the background scheduler loop."""
        self._scheduler_running = True
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop, daemon=True
        )
        self._scheduler_thread.start()

    def _scheduler_loop(self) -> None:
        """Check and run due tasks every second."""
        while self._scheduler_running:
            now = time.time()
            for task in list(self._scheduled):
                if not task.enabled:
                    continue
                should_run = False
                if task.run_at and now >= task.run_at and task.run_count == 0:
                    should_run = True
                elif task.interval_seconds:
                    last = task.last_run or 0
                    if now - last >= task.interval_seconds:
                        should_run = True

                if should_run:
                    task.last_run = now
                    task.run_count += 1
                    try:
                        task.func()
                    except Exception as exc:  # noqa: BLE001
                        log.error("Scheduled task '%s' failed: %s", task.name, exc)

            time.sleep(1)

    # ─── Persistence ──────────────────────────────────────────────────────

    def save_automation(self, automation: Automation) -> None:
        """Save automation to JSON file."""
        path = self._scripts_dir / f"{automation.name}.json"
        path.write_text(json.dumps(automation.to_dict(), indent=2), encoding="utf-8")
        log.info("Automation saved: %s", path)

    def _load_automation(self, name: str) -> Optional[Automation]:
        """Load automation from JSON file."""
        path = self._scripts_dir / f"{name}.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            automation = Automation.from_dict(data)
            self._automations[name] = automation
            return automation
        except Exception as exc:  # noqa: BLE001
            log.error("Failed to load automation '%s': %s", name, exc)
            return None

    def list_automations(self) -> list[str]:
        """Return names of all saved automations."""
        names = [p.stem for p in self._scripts_dir.glob("*.json")]
        return sorted(names)

    # ─── Built-in Templates ───────────────────────────────────────────────

    def cleanup_downloads(self, downloads_path: Optional[str] = None) -> None:
        """
        Built-in template: move old files from Downloads by type.

        Moves images → Pictures, documents → Documents, etc.
        """
        from pathlib import Path as _Path
        from utils.helpers import get_common_paths
        import shutil

        paths = get_common_paths()
        src = _Path(downloads_path) if downloads_path else paths.get("downloads", _Path.home() / "Downloads")

        type_map = {
            (".jpg", ".jpeg", ".png", ".gif", ".bmp"): paths.get("pictures"),
            (".mp4", ".mkv", ".avi", ".mov"): paths.get("videos"),
            (".mp3", ".wav", ".flac"): paths.get("music"),
            (".pdf", ".doc", ".docx", ".txt"): paths.get("documents"),
        }

        moved = 0
        for item in src.iterdir():
            if not item.is_file():
                continue
            ext = item.suffix.lower()
            for exts, dest_dir in type_map.items():
                if ext in exts and dest_dir and dest_dir.exists():
                    dest = dest_dir / item.name
                    if not dest.exists():
                        shutil.move(str(item), str(dest))
                        moved += 1
                    break

        log.info("cleanup_downloads: moved %d files from %s", moved, src)

    def shutdown(self) -> None:
        """Stop the scheduler."""
        self._scheduler_running = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=3)
