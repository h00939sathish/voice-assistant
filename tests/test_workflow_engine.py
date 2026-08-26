"""
Unit tests for WorkflowEngine YAML routine parsing and execution.
"""

from unittest.mock import ANY, AsyncMock

import pytest

from assistant.skill_router import SkillRouter
from assistant.workflow_engine import WorkflowEngine


@pytest.fixture
def loaded_router():
    return SkillRouter()


def test_workflow_engine_loading():
    """Verify loading YAML workflow routines."""
    engine = WorkflowEngine()
    workflows = engine.list_workflows()

    assert len(workflows) >= 1
    names = [wf["name"] for wf in workflows]
    assert "good_morning" in names


@pytest.mark.asyncio
async def test_workflow_execution():
    """Verify executing a workflow routine returns step results."""
    engine = WorkflowEngine()
    result = await engine.execute_workflow("good_morning")

    assert result["status"] == "completed"
    assert result["workflow"] == "good_morning"
    assert result["total_steps"] == 3
    assert len(result["steps"]) == 3


@pytest.mark.asyncio
async def test_execute_workflow_runs_skill_through_router(loaded_router, tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(
        "name: test_wf\nsteps:\n  - skill: time\n    text: what time is it\n"
    )
    loaded_router._execute_skill = AsyncMock(return_value="ok")
    engine = WorkflowEngine(workflows_dir=tmp_path)
    result = await engine.execute_workflow("test_wf", skill_router=loaded_router)
    assert result["status"] == "completed"
    loaded_router._execute_skill.assert_awaited_once_with(
        "time", "what time is it", ANY
    )
    assert result["steps"][0]["status"] == "completed"


@pytest.mark.asyncio
async def test_execute_workflow_marks_failed_step_failed(tmp_path):
    class Boom:
        async def execute(self, name, text, context=None):
            raise RuntimeError("boom")

    wf_file = tmp_path / "bad.yaml"
    wf_file.write_text("name: bad\nsteps:\n  - skill: time\n    text: x\n")
    engine = WorkflowEngine(workflows_dir=tmp_path)
    result = await engine.execute_workflow("bad", skill_router=Boom())
    assert result["steps"][0]["status"] == "failed"
    assert "boom" in result["steps"][0]["error"]
