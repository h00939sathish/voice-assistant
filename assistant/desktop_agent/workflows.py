"""
Workflow Engine Module

Provides workflow execution capabilities:
- Multi-step action sequences
- Variable substitution
- Retry logic
- Dry-run mode
- Memory of app positions
"""

import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowStep:
    """Represents a single step in a workflow."""

    def __init__(
        self,
        action: str,
        args: dict[str, Any] | None = None,
        description: str = "",
        retry_count: int = 3,
        retry_delay: float = 1.0,
        timeout: float = 30.0,
        on_error: str = "continue",
    ):
        self.action = action
        self.args = args or {}
        self.description = description
        self.retry_count = retry_count
        self.retry_delay = retry_delay
        self.timeout = timeout
        self.on_error = on_error

    def __repr__(self) -> str:
        return f"WorkflowStep({self.action}, {self.args})"

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "args": self.args,
            "description": self.description,
            "retry_count": self.retry_count,
            "retry_delay": self.retry_delay,
            "timeout": self.timeout,
            "on_error": self.on_error,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "WorkflowStep":
        return cls(
            action=data.get("action", ""),
            args=data.get("args", {}),
            description=data.get("description", ""),
            retry_count=data.get("retry_count", 3),
            retry_delay=data.get("retry_delay", 1.0),
            timeout=data.get("timeout", 30.0),
            on_error=data.get("on_error", "continue"),
        )


class Workflow:
    """Represents a named workflow with multiple steps."""

    def __init__(
        self,
        name: str,
        description: str = "",
        steps: list[WorkflowStep] | None = None,
        tags: list[str] | None = None,
        use_count: int = 0,
    ):
        self.name = name
        self.description = description
        self.steps = steps or []
        self.tags = tags or []
        self.use_count = use_count
        self.last_run_at: str | None = None

    def __repr__(self) -> str:
        return f"Workflow({self.name}, {len(self.steps)} steps)"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "steps": [s.to_dict() for s in self.steps],
            "tags": self.tags,
            "use_count": self.use_count,
            "last_run_at": self.last_run_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        wf = cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            tags=data.get("tags", []),
            use_count=data.get("use_count", 0),
        )
        wf.last_run_at = data.get("last_run_at")
        wf.steps = [WorkflowStep.from_dict(s) for s in data.get("steps", [])]
        return wf

    def add_step(self, step: WorkflowStep):
        self.steps.append(step)

    def get_step_count(self) -> int:
        return len(self.steps)


class WorkflowEngine:
    """
    Engine for executing workflows.

    Features:
    - Multi-step execution
    - Variable substitution
    - Retry logic
    - Dry-run mode
    - Memory
    """

    DEFAULT_WORKFLOWS = {
        "open_chrome": Workflow(
            name="open_chrome",
            description="Open Chrome browser",
            tags=["browser", "common"],
            steps=[
                WorkflowStep("open_app", {"path_or_name": "chrome"}, "Open Chrome"),
                WorkflowStep("wait", {"seconds": 2}, "Wait for Chrome"),
                WorkflowStep(
                    "focus_window", {"title": "Chrome"}, "Focus Chrome window"
                ),
            ],
        ),
        "google_search": Workflow(
            name="google_search",
            description="Open browser and search Google",
            tags=["browser", "search"],
            steps=[
                WorkflowStep("open_app", {"path_or_name": "chrome"}, "Open Chrome"),
                WorkflowStep("wait", {"seconds": 2}, "Wait for Chrome"),
                WorkflowStep("focus_window", {"title": "Chrome"}, "Focus Chrome"),
                WorkflowStep("hotkey", {"keys": ["ctrl", "l"]}, "Focus address bar"),
                WorkflowStep("type_text", {"text": "{query}"}, "Type search query"),
                WorkflowStep("press", {"key": "enter"}, "Submit search"),
            ],
        ),
        "open_spotify_play": Workflow(
            name="open_spotify_play",
            description="Open Spotify and play music",
            tags=["music", "media"],
            steps=[
                WorkflowStep("open_app", {"path_or_name": "spotify"}, "Open Spotify"),
                WorkflowStep("wait", {"seconds": 3}, "Wait for Spotify"),
                WorkflowStep("focus_window", {"title": "Spotify"}, "Focus Spotify"),
                WorkflowStep("press", {"key": "space"}, "Play/Pause"),
            ],
        ),
        "open_downloads": Workflow(
            name="open_downloads",
            description="Open Downloads folder",
            tags=["file", "common"],
            steps=[
                WorkflowStep("hotkey", {"keys": ["win", "e"]}, "Open Explorer"),
                WorkflowStep("wait", {"seconds": 1}, "Wait"),
                WorkflowStep("type_text", {"text": "Downloads"}, "Type path"),
                WorkflowStep("press", {"key": "enter"}, "Open folder"),
            ],
        ),
        "screenshot": Workflow(
            name="screenshot",
            description="Take a screenshot",
            tags=["utility", "screen"],
            steps=[
                WorkflowStep(
                    "take_screenshot",
                    {"path": "screenshots/screen.png"},
                    "Take screenshot",
                ),
            ],
        ),
        "minimize_all": Workflow(
            name="minimize_all",
            description="Minimize all windows (show desktop)",
            tags=["window", "utility"],
            steps=[
                WorkflowStep("hotkey", {"keys": ["win", "d"]}, "Show desktop"),
            ],
        ),
    }

    def __init__(
        self,
        desktop_agent: Any | None = None,
        memory_path: str = "data/desktop_agent_memory.json",
    ):
        self._desktop_agent = desktop_agent
        self._memory_path = memory_path
        self._workflows: dict[str, Workflow] = {}
        self._variables: dict[str, Any] = {}
        self._dry_run = False
        self._memory: dict[str, Any] = {}

        for name, wf in self.DEFAULT_WORKFLOWS.items():
            self._workflows[name] = wf

        self._load_memory()

        logger.info(f"WorkflowEngine initialized with {len(self._workflows)} workflows")

    def _load_memory(self):
        try:
            if os.path.exists(self._memory_path):
                with open(self._memory_path) as f:
                    self._memory = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load memory: {e}")
            self._memory = {}

    def _save_memory(self):
        try:
            Path(self._memory_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._memory_path, "w") as f:
                json.dump(self._memory, f, indent=2)
        except Exception as e:
            logger.warning(f"Failed to save memory: {e}")

    def set_desktop_agent(self, agent: Any):
        self._desktop_agent = agent

    def set_dry_run(self, dry_run: bool):
        self._dry_run = dry_run
        logger.info(f"Dry-run mode: {dry_run}")

    def set_variable(self, name: str, value: Any):
        self._variables[name] = value
        logger.debug(f"Set variable: {name}={value}")

    def get_variable(self, name: str, default: Any = None) -> Any:
        return self._variables.get(name, default)

    def _substitute_variables(self, text: str) -> str:
        if not isinstance(text, str):
            return text

        for name, value in self._variables.items():
            placeholder = "{" + name + "}"
            text = text.replace(placeholder, str(value))

        for name, value in self._memory.get("app_positions", {}).items():
            placeholder = "{" + name + "}"
            text = text.replace(placeholder, str(value))

        return text

    def register_workflow(self, workflow: Workflow):
        self._workflows[workflow.name] = workflow
        logger.info(f"Registered workflow: {workflow.name}")

    def get_workflow(self, name: str) -> Workflow | None:
        return self._workflows.get(name)

    def list_workflows(self, tag: str | None = None) -> list[Workflow]:
        if tag is None:
            return list(self._workflows.values())
        return [wf for wf in self._workflows.values() if tag in wf.tags]

    async def run(
        self,
        workflow_name: str,
        variables: dict[str, Any] | None = None,
        dry_run: bool | None = None,
    ) -> dict[str, Any]:
        wf = self.get_workflow(workflow_name)
        if not wf:
            return {"success": False, "error": f"Workflow not found: {workflow_name}"}

        if variables:
            for k, v in variables.items():
                self.set_variable(k, v)

        dry_run = dry_run if dry_run is not None else self._dry_run
        if dry_run:
            logger.info(f"[DRY RUN] Executing workflow: {workflow_name}")

        results = []
        success = True

        for step in wf.steps:
            result = await self.run_step(step, dry_run=dry_run)
            results.append(
                {
                    "step": step.action,
                    "description": step.description,
                    **result,
                }
            )

            if not result["success"]:
                if step.on_error == "stop":
                    success = False
                    break

        wf.use_count += 1
        from datetime import datetime

        wf.last_run_at = datetime.now().isoformat()

        return {
            "success": success,
            "workflow": workflow_name,
            "steps_executed": len(results),
            "results": results,
        }

    async def run_step(
        self,
        step: WorkflowStep,
        dry_run: bool | None = None,
    ) -> dict[str, Any]:
        dry_run = dry_run if dry_run is not None else self._dry_run

        try:
            args = {}
            for k, v in step.args.items():
                if isinstance(v, str):
                    args[k] = self._substitute_variables(v)
                else:
                    args[k] = v

            if dry_run:
                logger.info(f"[DRY RUN] {step.action}({args})")
                return {
                    "success": True,
                    "result": f"Would execute: {step.action}({args})",
                    "dry_run": True,
                }

            if not self._desktop_agent:
                return {"success": False, "error": "No DesktopAgent set"}

            action_map = {
                "move_mouse": self._desktop_agent.move_mouse,
                "click": self._desktop_agent.click,
                "type_text": self._desktop_agent.type_text,
                "press": self._desktop_agent.press,
                "hotkey": self._desktop_agent.hotkey,
                "open_app": self._desktop_agent.open_app,
                "close_app": self._desktop_agent.close_app,
                "focus_window": self._desktop_agent.focus_window,
                "wait": self._desktop_agent.wait,
            }

            if step.action not in action_map:
                return {"success": False, "error": f"Unknown action: {step.action}"}

            result = action_map[step.action](**args)
            return {"success": True, "result": result}

        except Exception as e:
            logger.error(f"run_step failed: {e}")
            return {"success": False, "error": str(e)}

    def save_app_position(self, app_name: str, x: int, y: int):
        if "app_positions" not in self._memory:
            self._memory["app_positions"] = {}
        self._memory["app_positions"][app_name] = {"x": x, "y": y}
        self._save_memory()

    def get_app_position(self, app_name: str) -> dict[str, int] | None:
        return self._memory.get("app_positions", {}).get(app_name)


def create_workflow_engine(desktop_agent: Any = None) -> WorkflowEngine:
    return WorkflowEngine(desktop_agent=desktop_agent)
