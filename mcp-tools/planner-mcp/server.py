"""
Planner MCP Server — Exposes task graph tools via Model Context Protocol.
Runs as a standalone subprocess, communicating via stdio JSON-RPC.
"""

import json
import os
import sys

# Add this directory to path for local imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from planner_engine import PlannerEngine

# Initialize
mcp = FastMCP("Planner")
engine = PlannerEngine()


@mcp.tool()
def create_goal(title: str, description: str = "") -> str:
    """Create a new high-level goal or objective to plan and execute.

    Use this when the user wants to accomplish something that requires multiple steps.
    Returns the goal ID for use with other planner tools.

    Args:
        title: Short name for the goal (e.g. "Audit home network")
        description: Detailed description of what to accomplish
    """
    result = engine.create_goal(title, description)
    return json.dumps(result, indent=2)


@mcp.tool()
def add_tasks(goal_id: int, tasks: str) -> str:
    """Add a list of tasks/steps to an existing goal.

    Each task can depend on other tasks (by ID) to enforce execution order.
    Tasks should be a JSON array of objects with: title, description (optional),
    depends_on (optional array of task IDs), order_index (optional int).

    Args:
        goal_id: The goal to add tasks to
        tasks: JSON string — array of task objects, e.g. [{"title": "Scan network"}, {"title": "Check ports", "depends_on": [1]}]
    """
    try:
        task_list = json.loads(tasks) if isinstance(tasks, str) else tasks
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON for tasks parameter"})

    if not isinstance(task_list, list):
        return json.dumps({"error": "tasks must be a JSON array"})

    result = engine.add_tasks(goal_id, task_list)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_next_task(goal_id: int) -> str:
    """Get the next task that is ready to execute for a given goal.

    Returns the next pending task whose dependencies are all completed.
    If all tasks are done, returns the final goal status.

    Args:
        goal_id: The goal to get the next task for
    """
    result = engine.get_next_task(goal_id)
    return json.dumps(result, indent=2)


@mcp.tool()
def update_task_status(
    task_id: int, status: str, result: str = "", error: str = ""
) -> str:
    """Update the status of a task after execution.

    When a task is marked as 'failed', all dependent tasks are automatically skipped.
    When all tasks are terminal, the goal is auto-completed or auto-failed.

    Args:
        task_id: The task to update
        status: New status — one of: running, completed, failed, skipped
        result: Result text (for completed tasks)
        error: Error message (for failed tasks)
    """
    result_data = engine.update_task_status(task_id, status, result, error)
    return json.dumps(result_data, indent=2)


@mcp.tool()
def replan(goal_id: int, new_tasks: str) -> str:
    """Cancel remaining pending tasks and replace with a new plan.

    Use this when the current plan needs to change due to failures or new information.
    Already completed/running tasks are preserved. Only pending tasks are cancelled.

    Args:
        goal_id: The goal to replan
        new_tasks: JSON string — array of new task objects (same format as add_tasks)
    """
    try:
        task_list = json.loads(new_tasks) if isinstance(new_tasks, str) else new_tasks
    except json.JSONDecodeError:
        return json.dumps({"error": "Invalid JSON for new_tasks parameter"})

    result = engine.replan(goal_id, task_list)
    return json.dumps(result, indent=2)


@mcp.tool()
def get_goal_status(goal_id: int) -> str:
    """Get a full progress report for a goal including all tasks and their statuses.

    Returns completion percentage, task breakdown by status, and individual task details.

    Args:
        goal_id: The goal to get status for
    """
    result = engine.get_goal_status(goal_id)
    return json.dumps(result, indent=2)


@mcp.tool()
def list_goals(status: str = "") -> str:
    """List all goals with summary progress information.

    Optionally filter by status (pending, active, completed, failed).

    Args:
        status: Optional status filter. Leave empty to show all goals.
    """
    result = engine.list_goals(status if status else None)
    return json.dumps(result, indent=2)


if __name__ == "__main__":
    mcp.run()
