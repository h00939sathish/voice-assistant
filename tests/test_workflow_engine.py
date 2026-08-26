"""
Unit tests for WorkflowEngine YAML routine parsing and execution.
"""

import pytest
import asyncio
from assistant.workflow_engine import WorkflowEngine


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

    assert result["status"] == "success"
    assert result["workflow"] == "good_morning"
    assert result["total_steps"] == 3
    assert len(result["step_results"]) == 3
