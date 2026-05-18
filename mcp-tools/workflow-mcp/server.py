"""
Workflow MCP Server — Save and replay named multi-step automation workflows.
Think of it as a personal macro library for the AI agent.
"""

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from mcp.server.fastmcp import FastMCP
from workflow_store import WorkflowStore

mcp = FastMCP("WorkflowAutomation")
store = WorkflowStore()


@mcp.tool()
def save_workflow(name: str, description: str, steps: str, tags: str = "[]") -> str:
    """Save a named, reusable workflow (macro) as a sequence of tool steps.

    Workflows are saved persistently and can be retrieved and executed later
    by name. Supports {{input.variable}} placeholders in step args for
    parameterisation at runtime.

    Args:
        name: Unique workflow name (e.g. 'morning_routine', 'network_audit')
        description: What this workflow does
        steps: JSON array of step objects. Each step: {"tool": str, "server": str,
               "args": dict, "description": str}. Example:
               [{"tool": "store_memory", "server": "mcp__memory",
                 "args": {"content": "{{input.note}}", "category": "context"}}]
        tags: JSON array of string tags for organisation, e.g. '["daily", "system"]'
    """
    try:
        step_list = json.loads(steps) if isinstance(steps, str) else steps
        tag_list = json.loads(tags) if isinstance(tags, str) else tags
    except json.JSONDecodeError as e:
        return json.dumps({"error": f"Invalid JSON: {e}"})

    if not isinstance(step_list, list):
        return json.dumps({"error": "steps must be a JSON array"})

    is_new = store.save_workflow(name, description, step_list, tag_list)
    return json.dumps(
        {
            "name": name,
            "saved": True,
            "is_new": is_new,
            "step_count": len(step_list),
            "tags": tag_list,
        },
        indent=2,
    )


@mcp.tool()
def get_workflow(name: str) -> str:
    """Retrieve a saved workflow and all its steps by name.

    Returns the full workflow definition including ordered steps with their
    tools, servers, and argument templates.

    Args:
        name: Workflow name to retrieve
    """
    wf = store.get_workflow(name)
    if not wf:
        return json.dumps({"error": f"Workflow '{name}' not found"})
    return json.dumps(wf, indent=2)


@mcp.tool()
def list_workflows(tag: str = "") -> str:
    """List all saved workflows with step counts and usage stats.

    Optionally filter by tag. Results are sorted by most used first.

    Args:
        tag: Optional tag to filter by (e.g. 'daily', 'system', 'network')
    """
    workflows = store.list_workflows(tag if tag else None)
    return json.dumps(
        {
            "total": len(workflows),
            "tag_filter": tag or None,
            "workflows": [
                {
                    "name": w["name"],
                    "description": w["description"],
                    "tags": w["tags"],
                    "step_count": w["step_count"],
                    "use_count": w["use_count"],
                    "last_run_at": w["last_run_at"],
                }
                for w in workflows
            ],
        },
        indent=2,
    )


@mcp.tool()
def delete_workflow(name: str) -> str:
    """Delete a saved workflow by name. This is irreversible.

    Args:
        name: Workflow name to delete
    """
    deleted = store.delete_workflow(name)
    return json.dumps(
        {
            "name": name,
            "deleted": deleted,
            "message": "Workflow deleted"
            if deleted
            else f"Workflow '{name}' not found",
        },
        indent=2,
    )


@mcp.tool()
def render_workflow(name: str, inputs: str = "{}") -> str:
    """Render a workflow's steps with input variable substitution applied.

    Replaces {{input.variable}} placeholders in step args with values from
    the inputs dict. Returns the fully resolved step list ready for execution.

    Args:
        name: Workflow name to render
        inputs: JSON object of input variables, e.g. '{"goal_title": "Audit network"}'
    """
    try:
        inputs_dict = json.loads(inputs) if isinstance(inputs, str) else inputs
    except json.JSONDecodeError:
        inputs_dict = {}

    rendered = store.render_workflow(name, inputs_dict)
    if rendered is None:
        return json.dumps({"error": f"Workflow '{name}' not found"})

    return json.dumps(
        {
            "name": name,
            "inputs": inputs_dict,
            "steps": rendered,
            "step_count": len(rendered),
        },
        indent=2,
    )


@mcp.tool()
def record_workflow_run(name: str) -> str:
    """Record that a workflow was executed (increments use count and updates last_run_at).

    Call this after successfully completing a workflow execution so usage
    stats are tracked and the workflow ranks higher in list_workflows.

    Args:
        name: Workflow name that was run
    """
    store.record_run(name)
    return json.dumps({"name": name, "recorded": True}, indent=2)


if __name__ == "__main__":
    mcp.run()
