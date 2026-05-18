"""
Task Executor — Minimal state machine for multi-step task orchestration.

First-build scope:
- Task state model: PENDING → RUNNING → PAUSED → COMPLETED | FAILED
- Step execution loop using tool_runner.execute() per step
- Pause/resume: serialize task state to data/task_state.json, restore on restart
- Basic verification hooks: after final step, run a validation callback

Recurring workflows (daily brief, scheduled summaries) are deferred to Phase 2.
"""

import copy
import json
import logging
import threading
import uuid
from collections.abc import Callable, Coroutine
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Task state model
# ---------------------------------------------------------------------------


class TaskState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskStep:
    """A single step in a multi-step task."""

    tool_name: str
    args: dict[str, Any]
    description: str = ""
    status: str = "pending"  # pending | running | done | failed | skipped
    result_status: str | None = None
    result: str | None = None
    error: str | None = None


@dataclass
class Task:
    """Represents a multi-step task."""

    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    goal: str = ""
    steps: list[TaskStep] = field(default_factory=list)
    state: TaskState = TaskState.PENDING
    current_step_index: int = 0
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())
    error: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "goal": self.goal,
            "steps": [
                {
                    "tool_name": s.tool_name,
                    "args": s.args,
                    "description": s.description,
                    "status": s.status,
                    "result_status": s.result_status,
                    "result": s.result,
                    "error": s.error,
                }
                for s in self.steps
            ],
            "state": self.state.value,
            "current_step_index": self.current_step_index,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "error": self.error,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Task":
        steps = [
            TaskStep(
                tool_name=s["tool_name"],
                args=s.get("args", {}),
                description=s.get("description", ""),
                status=s.get("status", "pending"),
                result_status=s.get("result_status"),
                result=s.get("result"),
                error=s.get("error"),
            )
            for s in data.get("steps", [])
        ]
        return cls(
            id=data.get("id", str(uuid.uuid4())[:8]),
            goal=data.get("goal", ""),
            steps=steps,
            state=TaskState(data.get("state", "pending")),
            current_step_index=data.get("current_step_index", 0),
            created_at=data.get("created_at", datetime.now().isoformat()),
            updated_at=data.get("updated_at", datetime.now().isoformat()),
            error=data.get("error"),
        )


# ---------------------------------------------------------------------------
# Task Executor
# ---------------------------------------------------------------------------


class TaskExecutor:
    """
    Runs multi-step tasks sequentially through tool_runner, with
    pause/resume and state persistence.

    Usage:
        executor = TaskExecutor(tool_runner)
        task = executor.create_task("Summarize inbox", [
            TaskStep(tool_name="search_web", args={"query": "inbox"}, description="Search"),
            TaskStep(tool_name="send_email", args={...}, description="Reply"),
        ])
        result = await executor.run(task.id)
    """

    STATE_FILE = "task_state.json"

    def __init__(
        self,
        tool_runner,
        state_dir: Path | None = None,
        on_step_complete: Callable | None = None,
        verification_hook: Callable[["Task"], Coroutine] | None = None,
    ):
        from assistant.tool_runner import ToolRunner

        self._runner: ToolRunner = tool_runner
        self._tasks: dict[str, Task] = {}
        self._on_step_complete = on_step_complete
        self._verification_hook = verification_hook
        self._lock = threading.Lock()
        self._pause_requested: bool = False
        self._pause_target_task_id: str | None = None
        self._workflow_templates: dict[str, dict[str, Any]] = {}

        if state_dir is None:
            state_dir = Path(__file__).parent.parent / "data"
        state_dir.mkdir(parents=True, exist_ok=True)
        self._state_path = state_dir / self.STATE_FILE

        # Hydrate any previously persisted state
        self._load_state()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def create_task(self, goal: str, steps: list[TaskStep]) -> Task:
        """Create and register a new task."""
        task = Task(goal=goal, steps=steps)
        with self._lock:
            self._tasks[task.id] = task
        self._save_state()
        logger.info(f"Task created: {task.id} — {goal} ({len(steps)} steps)")
        return task

    async def run(self, task_id: str) -> Task:
        """Execute a task from its current step index."""
        with self._lock:
            task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Unknown task: {task_id}")

        task.state = TaskState.RUNNING
        task.updated_at = datetime.now().isoformat()
        if self._pause_target_task_id == task.id:
            self._pause_requested = False
            self._pause_target_task_id = None
        self._save_state()
        self._emit_event("task_started", task)

        while task.current_step_index < len(task.steps):
            # Check for pause
            should_pause = self._pause_requested and (
                self._pause_target_task_id is None
                or self._pause_target_task_id == task.id
            )
            if should_pause:
                task.state = TaskState.PAUSED
                task.updated_at = datetime.now().isoformat()
                self._pause_requested = False
                self._pause_target_task_id = None
                self._save_state()
                logger.info(f"Task {task.id} paused at step {task.current_step_index}")
                self._emit_event("task_paused", task)
                return task

            step = task.steps[task.current_step_index]
            step.status = "running"
            task.updated_at = datetime.now().isoformat()

            try:
                result = await self._runner.execute(
                    step.tool_name,
                    step.args,
                    user_intent=task.goal,
                )
                step.result_status = result.status.value
                step.result = result.to_content_str()
                step.status = "done" if result.status.value == "ok" else "failed"
                step.error = result.error

                if self._on_step_complete:
                    try:
                        self._on_step_complete(task, step, result)
                    except Exception:
                        pass

                # If step failed with a non-retryable error, fail the whole task
                if step.status == "failed" and result.status.value not in (
                    "retryable",
                ):
                    task.state = TaskState.FAILED
                    task.error = step.error
                    task.updated_at = datetime.now().isoformat()
                    self._save_state()
                    self._emit_event("task_failed", task)
                    return task

            except Exception as e:
                step.status = "failed"
                step.error = str(e)
                task.state = TaskState.FAILED
                task.error = str(e)
                task.updated_at = datetime.now().isoformat()
                self._save_state()
                self._emit_event("task_failed", task)
                return task

            task.current_step_index += 1
            task.updated_at = datetime.now().isoformat()
            self._save_state()

        # All steps complete — run verification if available
        task.state = TaskState.COMPLETED
        task.updated_at = datetime.now().isoformat()

        if self._verification_hook:
            try:
                await self._verification_hook(task)
            except Exception as e:
                logger.warning(f"Verification hook failed for task {task.id}: {e}")
                task.error = f"Verification warning: {e}"

        self._save_state()
        self._emit_event("task_completed", task)
        logger.info(f"Task {task.id} completed")
        return task

    def pause(self, task_id: str | None = None):
        """Request a pause. The task will pause before the next step."""
        self._pause_requested = True
        self._pause_target_task_id = task_id
        if task_id:
            with self._lock:
                task = self._tasks.get(task_id)
            if task and task.state not in {TaskState.COMPLETED, TaskState.FAILED}:
                task.state = TaskState.PAUSED
                task.updated_at = datetime.now().isoformat()
                self._save_state()
        logger.info(f"Pause requested for {'current' if not task_id else task_id}")

    async def resume(self, task_id: str) -> Task:
        """Resume a paused task."""
        with self._lock:
            task = self._tasks.get(task_id)
        if not task:
            raise ValueError(f"Unknown task: {task_id}")
        if task.state != TaskState.PAUSED:
            raise ValueError(f"Task {task_id} is not paused (state={task.state})")

        self._emit_event("task_resumed", task)
        return await self.run(task_id)

    def get_active_task(self) -> Task | None:
        """Return the most recently updated RUNNING task, if any."""
        with self._lock:
            running = [t for t in self._tasks.values() if t.state == TaskState.RUNNING]
        if not running:
            return None
        return sorted(running, key=lambda t: t.updated_at, reverse=True)[0]

    def get_latest_paused_task(self) -> Task | None:
        """Return the most recently updated PAUSED task, if any."""
        with self._lock:
            paused = [t for t in self._tasks.values() if t.state == TaskState.PAUSED]
        if not paused:
            return None
        return sorted(paused, key=lambda t: t.updated_at, reverse=True)[0]

    def get_task_summary(self) -> str:
        """Human-readable task status summary for conversational use."""
        active = self.get_active_task()
        if active:
            step_total = len(active.steps)
            current = (
                min(active.current_step_index + 1, step_total) if step_total else 0
            )
            return (
                f"Active task {active.id}: {active.goal} (step {current}/{step_total})"
            )

        paused = self.get_latest_paused_task()
        if paused:
            step_total = len(paused.steps)
            current = (
                min(paused.current_step_index + 1, step_total) if step_total else 0
            )
            return (
                f"Paused task {paused.id}: {paused.goal} (step {current}/{step_total})"
            )

        with self._lock:
            recent = sorted(
                self._tasks.values(), key=lambda t: t.updated_at, reverse=True
            )
        if recent:
            latest = recent[0]
            return f"Latest task {latest.id}: {latest.goal} [{latest.state.value}]"

        return "No tasks are active right now."

    def register_workflow(
        self, name: str, steps: list[TaskStep], description: str = ""
    ) -> bool:
        """Register a reusable workflow template."""
        workflow_name = (name or "").strip().lower()
        if not workflow_name or not steps:
            return False
        with self._lock:
            self._workflow_templates[workflow_name] = {
                "name": workflow_name,
                "description": description.strip(),
                "steps": copy.deepcopy(steps),
                "updated_at": datetime.now().isoformat(),
            }
        return True

    def list_workflows(self) -> list[dict[str, Any]]:
        """Return registered workflow metadata."""
        with self._lock:
            templates = list(self._workflow_templates.values())
        return [
            {
                "name": wf["name"],
                "description": wf.get("description", ""),
                "step_count": len(wf.get("steps", [])),
                "updated_at": wf.get("updated_at"),
            }
            for wf in templates
        ]

    def create_task_from_workflow(
        self, name: str, goal: str | None = None
    ) -> Task | None:
        """Create a task instance from a named workflow template."""
        workflow_name = (name or "").strip().lower()
        with self._lock:
            wf = self._workflow_templates.get(workflow_name)
        if not wf:
            return None
        steps = copy.deepcopy(wf["steps"])
        task_goal = goal or f"Run workflow: {workflow_name}"
        return self.create_task(task_goal, steps)

    def get_task(self, task_id: str) -> Task | None:
        with self._lock:
            return self._tasks.get(task_id)

    def get_all_tasks(self) -> list[Task]:
        with self._lock:
            return list(self._tasks.values())

    def get_pending_tasks(self) -> list[Task]:
        """Tasks that were interrupted (paused/pending) and can be resumed."""
        with self._lock:
            return [
                t
                for t in self._tasks.values()
                if t.state in (TaskState.PENDING, TaskState.PAUSED)
            ]

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save_state(self):
        """Persist all task states to JSON."""
        try:
            with self._lock:
                data = {
                    "tasks": {tid: t.to_dict() for tid, t in self._tasks.items()},
                    "saved_at": datetime.now().isoformat(),
                }
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, default=str)
        except Exception as e:
            logger.warning(f"Failed to save task state: {e}")

    def _load_state(self):
        """Recover task state from disk on startup."""
        if not self._state_path.exists():
            return
        try:
            with open(self._state_path, encoding="utf-8") as f:
                data = json.load(f)
            with self._lock:
                for tid, tdata in data.get("tasks", {}).items():
                    self._tasks[tid] = Task.from_dict(tdata)
            pending = self.get_pending_tasks()
            if pending:
                logger.info(f"Recovered {len(pending)} pending task(s) from disk")
        except Exception as e:
            logger.warning(f"Failed to load task state: {e}")

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def _emit_event(self, event_name: str, task: Task):
        """Publish task lifecycle events to the event bus."""
        try:
            from assistant.events import StatusEvent, TaskLifecycleEvent, bus

            bus.publish(
                TaskLifecycleEvent(
                    task_id=task.id,
                    action=event_name.replace("task_", ""),
                    goal=task.goal,
                    source="task_executor",
                )
            )
            bus.publish(
                StatusEvent(
                    text=f"[{event_name}] Task {task.id}: {task.goal}",
                    source="task_executor",
                )
            )
        except Exception:
            pass
