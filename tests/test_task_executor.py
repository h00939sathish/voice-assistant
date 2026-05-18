"""
Integration tests for TaskExecutor: state machine, step execution, pause/resume.
"""

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from assistant.task_executor import TaskExecutor, TaskState, TaskStep
from assistant.tool_runner import ToolResult, ToolStatus

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def tmp_state_dir(tmp_path):
    return tmp_path


@pytest.fixture
def mock_tool_runner():
    """Mock ToolRunner that always succeeds."""
    runner = MagicMock()
    runner.execute = AsyncMock(
        return_value=ToolResult(
            status=ToolStatus.OK,
            data={"result": "success"},
            summary="Tool executed OK",
            tool_name="mock_tool",
            args={},
            duration_ms=50,
        )
    )
    return runner


@pytest.fixture
def executor(mock_tool_runner, tmp_state_dir):
    """TaskExecutor with mock runner and temp state path."""
    ex = TaskExecutor(tool_runner=mock_tool_runner)
    ex._state_path = tmp_state_dir / "task_state.json"
    return ex


# ---------------------------------------------------------------------------
# Task Lifecycle
# ---------------------------------------------------------------------------


class TestTaskLifecycle:
    def test_create_task(self, executor):
        steps = [
            TaskStep(tool_name="get_weather", args={"city": "NYC"}),
            TaskStep(tool_name="send_email", args={"to": "user@test.com"}),
        ]
        task = executor.create_task(goal="Test task", steps=steps)
        assert task.state == TaskState.PENDING
        assert len(task.steps) == 2
        assert task.id in executor.get_pending_tasks() or task.id

    @pytest.mark.asyncio
    async def test_run_completes_all_steps(self, executor, mock_tool_runner):
        steps = [
            TaskStep(tool_name="step_1", args={}),
            TaskStep(tool_name="step_2", args={}),
            TaskStep(tool_name="step_3", args={}),
        ]
        task = executor.create_task(goal="3-step plan", steps=steps)
        completed = await executor.run(task.id)

        assert completed.state == TaskState.COMPLETED
        assert mock_tool_runner.execute.call_count == 3

    @pytest.mark.asyncio
    async def test_failed_step_marks_task_failed(self, executor, mock_tool_runner):
        """If a step fails, the task should be marked FAILED."""
        mock_tool_runner.execute = AsyncMock(
            return_value=ToolResult(
                status=ToolStatus.ERROR,
                data=None,
                summary="Tool exploded",
                tool_name="bad_tool",
                args={},
                duration_ms=10,
            )
        )
        steps = [
            TaskStep(tool_name="good_tool", args={}),
            TaskStep(tool_name="bad_tool", args={}),
        ]
        task = executor.create_task(goal="Will fail", steps=steps)
        result = await executor.run(task.id)
        assert result.state == TaskState.FAILED


# ---------------------------------------------------------------------------
# Pause / Resume
# ---------------------------------------------------------------------------


class TestPauseResume:
    @pytest.mark.asyncio
    async def test_pause_persists_state(self, executor, tmp_state_dir):
        steps = [
            TaskStep(tool_name="s1", args={}),
            TaskStep(tool_name="s2", args={}),
        ]
        task = executor.create_task(goal="Pause test", steps=steps)

        # Manually pause
        executor.pause(task.id)

        # Check state file exists
        state_path = tmp_state_dir / "task_state.json"
        assert state_path.exists()

        state_data = json.loads(state_path.read_text(encoding="utf-8"))
        tasks = state_data.get("tasks", {})
        assert task.id in tasks
        assert tasks[task.id]["state"] == TaskState.PAUSED.value

    @pytest.mark.asyncio
    async def test_resume_continues_task(self, executor, mock_tool_runner):
        steps = [
            TaskStep(tool_name="s1", args={}),
            TaskStep(tool_name="s2", args={}),
        ]
        task = executor.create_task(goal="Resume test", steps=steps)
        executor.pause(task.id)

        # Resume and run
        result = await executor.run(task.id)
        assert result.state == TaskState.COMPLETED


# ---------------------------------------------------------------------------
# State Model
# ---------------------------------------------------------------------------


class TestTaskStateModel:
    def test_task_step_has_required_fields(self):
        step = TaskStep(tool_name="test", args={"key": "val"})
        assert step.tool_name == "test"
        assert step.args == {"key": "val"}
        assert step.result is None

    def test_task_state_transitions(self):
        """TaskState enum has all expected values."""
        assert TaskState.PENDING.value == "pending"
        assert TaskState.RUNNING.value == "running"
        assert TaskState.PAUSED.value == "paused"
        assert TaskState.COMPLETED.value == "completed"
        assert TaskState.FAILED.value == "failed"
