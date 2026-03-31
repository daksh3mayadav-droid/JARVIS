"""
core/brain.py — Central reasoning engine for JARVIS

Connects to Ollama (localhost:11434), classifies intent,
dispatches to subsystems, manages conversation context,
and executes multi-step tasks autonomously.
"""

from __future__ import annotations

import json
import queue
import threading
import time
from typing import Any, Callable, Optional

import requests

from core.memory import Memory
from core.planner import Planner, Plan
from core.safety import SafetyClassifier, RiskLevel
from utils.helpers import get_config, safe_json_parse
from utils.logger import get_logger
from utils.tars_personality import TARSPersonality

log = get_logger("brain")

# ─── Intent Categories ────────────────────────────────────────────────────────

INTENTS = (
    "system_control",   # Mouse, keyboard, window management
    "file_ops",         # File operations
    "app_launch",       # Open/close applications
    "information",      # Query system info, weather, facts
    "settings",         # Windows settings, hardware config
    "automation",       # Record/replay, scheduled tasks
    "conversation",     # General chat
    "vision",           # Screen capture, OCR
    "search",           # File / web search
    "unknown",
)

# ─── System Prompt ────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are JARVIS, an advanced autonomous AI assistant inspired by TARS from Interstellar.
You are running locally on an HP Pavilion Gaming 15 (Ryzen 5 5600H, GTX 1650, 16GB RAM, Windows 11).

PERSONALITY: Dry, concise, slightly sarcastic but always helpful. Never over-explain.
Action-oriented: "Opening Steam..." not "I am now going to open Steam for you."
Honest about limitations. Never fabricate system data.

AVAILABLE CAPABILITIES:
- system_control: mouse click, keyboard input, window management
- file_ops: create/read/move/delete/search files and folders
- app_launch: open any installed application by name
- information: system stats (CPU, RAM, GPU, battery, network, storage)
- settings: navigate Windows 11 settings, toggle WiFi/Bluetooth/etc.
- automation: record/replay sequences, scheduled tasks
- vision: screenshot, OCR, screen analysis
- search: search files, web (via browser)
- conversation: general chat and questions

RESPONSE FORMAT:
Always respond with a JSON object in this format:
{
  "intent": "<one of the intent categories above>",
  "response": "<your TARS-style response to speak/display>",
  "action": "<specific action to perform>",
  "parameters": {<action parameters>},
  "steps": [<optional: list of step dicts for multi-step tasks>],
  "reasoning": "<brief explanation>"
}

For simple conversation with no system action needed, use intent "conversation" and leave action empty.
Always think before acting. Plans must be explicit. Never hallucinate system state."""


class Brain:
    """
    Central reasoning engine for JARVIS.

    Manages:
    - LLM connection via Ollama API
    - Intent classification and dispatch
    - Conversation history (last 20 messages)
    - Async task queue for long operations
    - Safety checks before execution
    """

    def __init__(
        self,
        memory: Optional[Memory] = None,
        planner: Optional[Planner] = None,
        safety: Optional[SafetyClassifier] = None,
        personality: Optional[TARSPersonality] = None,
    ) -> None:
        """
        Initialize the Brain.

        Args:
            memory: Memory instance for persistence.
            planner: Planner instance for multi-step task execution.
            safety: SafetyClassifier for risk assessment.
            personality: TARSPersonality for response formatting.
        """
        config = get_config()
        llm_cfg = config.get("llm", {})

        self.model = llm_cfg.get("model", "phi")
        self.api_url = llm_cfg.get("api_url", "http://localhost:11434")
        self.temperature = llm_cfg.get("temperature", 0.7)
        self.max_tokens = llm_cfg.get("max_tokens", 2048)
        self.timeout = llm_cfg.get("timeout", 60)
        self.retry_attempts = llm_cfg.get("retry_attempts", 3)

        self.memory = memory or Memory()
        self.planner = planner or Planner()
        self.safety = safety or SafetyClassifier()
        self.personality = personality or TARSPersonality()

        self._context: list[dict] = []  # Last 20 messages
        self._task_queue: queue.Queue = queue.Queue()
        self._action_registry: dict[str, Callable] = {}
        self._running = False
        self._worker_thread: Optional[threading.Thread] = None

        log.info("Brain initialized. Model: %s @ %s", self.model, self.api_url)

    # ─── Action Registry ──────────────────────────────────────────────────

    def register_action(self, name: str, handler: Callable) -> None:
        """
        Register an action handler callable.

        Args:
            name: Action key (e.g. 'open_app', 'take_screenshot').
            handler: Callable that accepts keyword arguments.
        """
        self._action_registry[name] = handler
        log.debug("Registered action: %s", name)

    def register_actions(self, registry: dict[str, Callable]) -> None:
        """Bulk-register action handlers."""
        self._action_registry.update(registry)

    # ─── Main Processing ──────────────────────────────────────────────────

    def process(self, user_input: str) -> str:
        """
        Process a user message end-to-end.

        1. Add to conversation context + memory
        2. Query the LLM
        3. Parse the structured JSON response
        4. Execute the specified action (with safety check)
        5. Return the TARS-style response string

        Args:
            user_input: Raw user input text.

        Returns:
            Response string to speak/display.
        """
        if not user_input.strip():
            return self.personality.respond("Say something.")

        log.info("Processing: %s", user_input[:100])
        self._add_context("user", user_input)
        self.memory.add_message("user", user_input)

        # Query LLM
        llm_raw = self._query_llm(user_input)
        if not llm_raw:
            return self.personality.error("No response from LLM. Is Ollama running?")

        # Parse structured response
        parsed = safe_json_parse(llm_raw)
        if not parsed or not isinstance(parsed, dict):
            # Fallback: treat raw text as conversation response
            response = self.personality.respond(llm_raw)
            self._add_context("assistant", response)
            self.memory.add_message("assistant", response)
            return response

        intent = parsed.get("intent", "conversation")
        response_text = parsed.get("response", "")
        action = parsed.get("action", "")
        parameters = parsed.get("parameters", {})
        steps_data = parsed.get("steps", [])

        log.info("Intent: %s | Action: %s", intent, action)

        # Apply personality to response
        response_styled = self.personality.respond(response_text, context=intent)

        # Execute action or multi-step plan
        if steps_data:
            self._execute_plan_async(parsed.get("reasoning", ""), steps_data)
        elif action and action in self._action_registry:
            exec_result = self._execute_action(action, parameters)
            if exec_result is not None and isinstance(exec_result, str):
                response_styled = exec_result
        elif action:
            log.warning("Unknown action '%s' — no handler registered.", action)

        self._add_context("assistant", response_styled)
        self.memory.add_message("assistant", response_styled)
        self.memory.learn_pattern(user_input, response_styled)

        return response_styled

    # ─── LLM Interface ────────────────────────────────────────────────────

    def _query_llm(self, prompt: str) -> Optional[str]:
        """
        Send a prompt to Ollama and return the raw text response.

        Args:
            prompt: The user prompt.

        Returns:
            LLM response text or None on failure.
        """
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self._context[-20:])

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": self.max_tokens,
            },
        }

        for attempt in range(1, self.retry_attempts + 1):
            try:
                resp = requests.post(
                    f"{self.api_url}/api/chat",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("message", {}).get("content", "")
                log.debug("LLM response received (%d chars)", len(content))
                return content
            except requests.exceptions.ConnectionError:
                log.error("Cannot connect to Ollama at %s", self.api_url)
                return None
            except requests.exceptions.Timeout:
                log.warning("LLM timeout (attempt %d/%d)", attempt, self.retry_attempts)
                if attempt == self.retry_attempts:
                    return None
                time.sleep(2)
            except Exception as exc:  # noqa: BLE001
                log.error("LLM query failed: %s", exc)
                return None

        return None

    def generate_plan_steps(self, goal: str) -> list[dict]:
        """
        Ask the LLM to break a complex goal into atomic steps.

        Args:
            goal: The high-level goal.

        Returns:
            List of step dicts suitable for Planner.build_plan().
        """
        prompt = (
            f"Break this goal into 3-8 atomic steps for execution:\n'{goal}'\n"
            f"Return JSON: {{\"steps\": ["
            f"{{\"description\": \"...\", \"action\": \"...\", "
            f"\"parameters\": {{}}, \"risk_level\": \"SAFE|RISKY|DANGEROUS\", "
            f"\"estimated_seconds\": 1}}]}}"
        )
        raw = self._query_llm(prompt)
        if not raw:
            return []
        parsed = safe_json_parse(raw)
        if parsed and isinstance(parsed, dict):
            return parsed.get("steps", [])
        return []

    # ─── Action Execution ─────────────────────────────────────────────────

    def _execute_action(
        self,
        action: str,
        parameters: dict,
    ) -> Optional[str]:
        """
        Execute a registered action with safety check.

        Args:
            action: Action key.
            parameters: Action parameters.

        Returns:
            Action result string or None.
        """
        description = f"{action}: {json.dumps(parameters)}"
        level = self.safety.classify(description)

        if level != RiskLevel.SAFE:
            confirmed = self.safety.request_confirmation(description, level)
            if not confirmed:
                return self.personality.respond("Action cancelled by user.")

        try:
            handler = self._action_registry[action]
            result = handler(**parameters)
            log.info("Action executed: %s", action)
            return str(result) if result is not None else None
        except Exception as exc:  # noqa: BLE001
            log.error("Action '%s' failed: %s", action, exc)
            return self.personality.error(str(exc))

    def _execute_plan_async(self, goal: str, steps_data: list[dict]) -> None:
        """
        Queue a multi-step plan for background execution.

        Args:
            goal: Plan goal description.
            steps_data: List of step dicts.
        """
        plan = self.planner.build_plan(goal, steps_data)
        self._task_queue.put(plan)

        if not self._running:
            self._start_worker()

    # ─── Worker Thread ────────────────────────────────────────────────────

    def _start_worker(self) -> None:
        """Start the background task worker thread."""
        self._running = True
        self._worker_thread = threading.Thread(
            target=self._worker_loop, daemon=True
        )
        self._worker_thread.start()
        log.debug("Task worker thread started.")

    def _worker_loop(self) -> None:
        """Background loop that processes queued plans."""
        while self._running:
            try:
                plan: Plan = self._task_queue.get(timeout=1.0)
                log.info("Worker: executing plan '%s'", plan.goal)
                self.planner.execute(plan, self._action_registry)
                self._task_queue.task_done()
            except queue.Empty:
                self._running = False
            except Exception as exc:  # noqa: BLE001
                log.error("Worker error: %s", exc)

    # ─── Context Management ───────────────────────────────────────────────

    def _add_context(self, role: str, content: str) -> None:
        """Add a message to the rolling context window (max 20)."""
        self._context.append({"role": role, "content": content})
        if len(self._context) > 20:
            self._context = self._context[-20:]

    def clear_context(self) -> None:
        """Clear the in-memory conversation context."""
        self._context.clear()
        log.info("Conversation context cleared.")

    def get_context(self) -> list[dict]:
        """Return a copy of the current conversation context."""
        return list(self._context)

    # ─── Status ───────────────────────────────────────────────────────────

    def is_ollama_running(self) -> bool:
        """
        Check if Ollama is reachable.

        Returns:
            True if the Ollama API responds, False otherwise.
        """
        try:
            resp = requests.get(f"{self.api_url}/api/tags", timeout=3)
            return resp.status_code == 200
        except Exception:  # noqa: BLE001
            return False

    def explain_state(self) -> str:
        """Return a description of the brain's current state."""
        plan_info = self.planner.explain_current_state()
        ctx_len = len(self._context)
        queue_size = self._task_queue.qsize()
        return (
            f"Brain state:\n"
            f"  Context: {ctx_len} messages\n"
            f"  Queue: {queue_size} pending tasks\n"
            f"  Planner: {plan_info}"
        )

    def shutdown(self) -> None:
        """Gracefully stop the brain worker thread."""
        self._running = False
        if self._worker_thread and self._worker_thread.is_alive():
            self._worker_thread.join(timeout=3)
        log.info("Brain shut down.")
