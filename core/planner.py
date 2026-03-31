"""
core/planner.py — Autonomous task planner for JARVIS

Breaks complex requests into atomic steps, estimates risk,
executes sequentially with progress reporting, and re-plans on failure.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Optional

from utils.logger import get_logger
from utils.tars_personality import TARSPersonality

log = get_logger("planner")


class StepStatus(Enum):
    """Execution state of an individual plan step."""
    PENDING = "pending"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass
class PlanStep:
    """A single atomic action in an execution plan."""

    index: int
    description: str
    action: str                          # Machine-readable action key
    parameters: dict = field(default_factory=dict)
    risk_level: str = "SAFE"
    estimated_seconds: float = 1.0
    status: StepStatus = StepStatus.PENDING
    result: Optional[Any] = None
    error: Optional[str] = None
    started_at: Optional[float] = None
    finished_at: Optional[float] = None

    def duration(self) -> Optional[float]:
        """Return actual execution duration in seconds, if completed."""
        if self.started_at and self.finished_at:
            return self.finished_at - self.started_at
        return None


@dataclass
class Plan:
    """A complete execution plan composed of ordered steps."""

    goal: str
    steps: list[PlanStep] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    completed: bool = False
    success: bool = False

    # ── Derived properties ───────────────────────────────────────────────

    @property
    def total(self) -> int:
        return len(self.steps)

    @property
    def done_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.DONE)

    @property
    def failed_count(self) -> int:
        return sum(1 for s in self.steps if s.status == StepStatus.FAILED)

    @property
    def pending_steps(self) -> list[PlanStep]:
        return [s for s in self.steps if s.status == StepStatus.PENDING]

    @property
    def progress_pct(self) -> float:
        if not self.steps:
            return 0.0
        return (self.done_count / len(self.steps)) * 100

    def visualize(self) -> str:
        """Return a human-readable numbered plan with status icons."""
        icons = {
            StepStatus.PENDING: "⏳",
            StepStatus.RUNNING: "🔄",
            StepStatus.DONE:    "✅",
            StepStatus.FAILED:  "❌",
            StepStatus.SKIPPED: "⏭️ ",
        }
        lines = [f"Plan: {self.goal}", "─" * 40]
        for step in self.steps:
            icon = icons[step.status]
            dur = f" ({step.duration():.1f}s)" if step.duration() else ""
            lines.append(f"  {step.index}. {icon} {step.description}{dur}")
            if step.error:
                lines.append(f"       ↳ Error: {step.error}")
        lines.append("─" * 40)
        lines.append(
            f"Progress: {self.done_count}/{self.total} steps "
            f"({self.progress_pct:.0f}%)"
        )
        return "\n".join(lines)


class Planner:
    """
    Autonomous task planner for JARVIS.

    Builds an execution plan from a natural-language goal,
    executes steps one by one with safety checks and progress reporting,
    and supports dynamic re-planning when a step fails.
    """

    def __init__(
        self,
        personality: Optional[TARSPersonality] = None,
        progress_callback: Optional[Callable[[Plan], None]] = None,
    ) -> None:
        """
        Initialize the planner.

        Args:
            personality: TARSPersonality for progress messages.
            progress_callback: Called after each step with the current Plan.
        """
        self.personality = personality or TARSPersonality()
        self.progress_callback = progress_callback
        self._current_plan: Optional[Plan] = None

    # ─── Plan Building ────────────────────────────────────────────────────

    def build_plan(self, goal: str, steps_data: list[dict]) -> Plan:
        """
        Build a :class:`Plan` from structured step data.

        Args:
            goal: Human-readable goal description.
            steps_data: List of dicts, each with keys:
                        description, action, parameters (opt),
                        risk_level (opt), estimated_seconds (opt).

        Returns:
            New :class:`Plan` ready for execution.
        """
        plan = Plan(goal=goal)
        for i, sd in enumerate(steps_data, start=1):
            step = PlanStep(
                index=i,
                description=sd.get("description", f"Step {i}"),
                action=sd.get("action", "noop"),
                parameters=sd.get("parameters", {}),
                risk_level=sd.get("risk_level", "SAFE"),
                estimated_seconds=sd.get("estimated_seconds", 1.0),
            )
            plan.steps.append(step)

        self._current_plan = plan
        log.info("Plan built: '%s' (%d steps)", goal, len(plan.steps))
        return plan

    def build_simple_plan(self, goal: str, action_func: Callable) -> Plan:
        """
        Build a one-step plan wrapping a single callable.

        Args:
            goal: Description of the goal.
            action_func: A zero-argument callable to execute.

        Returns:
            Single-step :class:`Plan`.
        """
        plan = Plan(goal=goal)
        plan.steps.append(
            PlanStep(
                index=1,
                description=goal,
                action="callable",
                parameters={"func": action_func},
            )
        )
        self._current_plan = plan
        return plan

    # ─── Execution ────────────────────────────────────────────────────────

    def execute(
        self,
        plan: Plan,
        action_registry: Optional[dict[str, Callable]] = None,
    ) -> bool:
        """
        Execute a :class:`Plan` step by step.

        Args:
            plan: The plan to execute.
            action_registry: Dict mapping action keys to callables.
                             Each callable receives (step.parameters).

        Returns:
            True if all steps completed successfully, False otherwise.
        """
        log.info("Executing plan: %s", plan.goal)
        print(f"\n{self.personality.planning()}")
        print(plan.visualize())
        print()

        for step in plan.steps:
            if step.status != StepStatus.PENDING:
                continue

            self._run_step(step, action_registry or {})
            self._report(plan)

            if step.status == StepStatus.FAILED:
                recovered = self._attempt_recovery(step, plan, action_registry or {})
                if not recovered:
                    log.error("Plan aborted at step %d: %s", step.index, step.description)
                    plan.completed = True
                    plan.success = False
                    return False

        plan.completed = True
        plan.success = True
        log.info("Plan completed successfully: %s", plan.goal)
        print(self.personality.complete(f"'{plan.goal}'"))
        return True

    def _run_step(
        self,
        step: PlanStep,
        action_registry: dict[str, Callable],
    ) -> None:
        """Execute a single step."""
        step.status = StepStatus.RUNNING
        step.started_at = time.time()
        log.debug("Running step %d: %s", step.index, step.description)

        try:
            if step.action == "callable" and "func" in step.parameters:
                result = step.parameters["func"]()
            elif step.action in action_registry:
                handler = action_registry[step.action]
                params = {k: v for k, v in step.parameters.items() if k != "func"}
                result = handler(**params)
            else:
                log.warning("Unknown action '%s', skipping.", step.action)
                step.status = StepStatus.SKIPPED
                step.finished_at = time.time()
                return

            step.result = result
            step.status = StepStatus.DONE
            log.debug("Step %d done in %.2fs", step.index, step.duration() or 0)

        except Exception as exc:  # noqa: BLE001
            step.status = StepStatus.FAILED
            step.error = str(exc)
            log.error("Step %d failed: %s", step.index, exc)
        finally:
            if step.finished_at is None:
                step.finished_at = time.time()

    # ─── Recovery ─────────────────────────────────────────────────────────

    def _attempt_recovery(
        self,
        failed_step: PlanStep,
        plan: Plan,
        action_registry: dict[str, Callable],
    ) -> bool:
        """
        Attempt to recover from a failed step.

        Strategy: retry the step once with the same parameters.

        Args:
            failed_step: The step that failed.
            plan: The parent plan.
            action_registry: Action callable registry.

        Returns:
            True if recovery succeeded, False otherwise.
        """
        log.warning("Attempting recovery for step %d…", failed_step.index)
        print(f"  ⚠️  Step failed: {failed_step.error}. Retrying once…")

        failed_step.status = StepStatus.PENDING
        failed_step.error = None
        self._run_step(failed_step, action_registry)

        if failed_step.status == StepStatus.DONE:
            log.info("Recovery succeeded for step %d.", failed_step.index)
            return True

        log.error("Recovery failed for step %d.", failed_step.index)
        return False

    # ─── Reporting ────────────────────────────────────────────────────────

    def _report(self, plan: Plan) -> None:
        """Emit progress updates."""
        if self.progress_callback:
            try:
                self.progress_callback(plan)
            except Exception as exc:  # noqa: BLE001
                log.debug("Progress callback error: %s", exc)

        # Print every 3 steps or on final step
        if plan.done_count % 3 == 0 or plan.done_count == plan.total:
            pct = plan.progress_pct
            print(f"  📊  Progress: {plan.done_count}/{plan.total} steps ({pct:.0f}%)")

    # ─── State ────────────────────────────────────────────────────────────

    @property
    def current_plan(self) -> Optional[Plan]:
        """Return the currently active plan."""
        return self._current_plan

    def explain_current_state(self) -> str:
        """
        Return a human-readable description of the current execution state.

        Returns:
            Descriptive string for status queries.
        """
        if not self._current_plan:
            return "No active plan."

        p = self._current_plan
        if p.completed:
            status = "completed successfully" if p.success else "failed"
            return f"Plan '{p.goal}' {status}. {p.done_count}/{p.total} steps done."

        running = [s for s in p.steps if s.status == StepStatus.RUNNING]
        if running:
            return (
                f"Executing plan '{p.goal}': "
                f"currently on step {running[0].index} — {running[0].description}. "
                f"Overall: {p.done_count}/{p.total} steps done."
            )

        return (
            f"Plan '{p.goal}' paused at step {p.done_count + 1}. "
            f"{p.done_count}/{p.total} steps done."
        )
