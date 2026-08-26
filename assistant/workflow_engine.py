"""
Workflow Engine - Parses and executes declarative YAML workflow routines.
"""

import asyncio
import logging
from pathlib import Path
from typing import Any
import yaml

logger = logging.getLogger(__name__)


class WorkflowEngine:
    """Parses and executes multi-step YAML workflow routines."""

    def __init__(self, workflows_dir: str | Path | None = None) -> None:
        if workflows_dir is None:
            workflows_dir = Path(__file__).parent.parent / "workflows"
        self.workflows_dir = Path(workflows_dir)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)
        self._workflows: dict[str, dict[str, Any]] = {}
        self.load_workflows()

    def load_workflows(self) -> None:
        """Scan directory and load all .yaml / .yml workflow files."""
        self._workflows.clear()
        for filepath in self.workflows_dir.glob("*.yaml"):
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    data = yaml.safe_yaml_load(f) if hasattr(yaml, "safe_yaml_load") else yaml.safe_load(f)
                    if isinstance(data, dict) and "name" in data:
                        self._workflows[data["name"].lower()] = data
                        logger.info(f"Loaded workflow routine: {data['name']}")
            except Exception as e:
                logger.warning(f"Failed to load workflow from {filepath}: {e}")

    def list_workflows(self) -> list[dict[str, str]]:
        """Return list of loaded workflow names and descriptions."""
        return [
            {
                "name": name,
                "description": wf.get("description", "No description provided"),
            }
            for name, wf in self._workflows.items()
        ]

    def get_workflow(self, name: str) -> dict[str, Any] | None:
        """Retrieve workflow definition by name."""
        return self._workflows.get(name.lower())

    async def execute_workflow(
        self, name: str, skill_router: Any = None
    ) -> dict[str, Any]:
        """Execute steps defined in a workflow routine."""
        wf = self.get_workflow(name)
        if not wf:
            return {"status": "error", "message": f"Workflow '{name}' not found."}

        steps = wf.get("steps", [])
        results = []
        logger.info(f"Executing workflow routine: {name} ({len(steps)} steps)")

        for step in steps:
            step_id = step.get("id", "step")
            skill_name = step.get("skill")
            action = step.get("action")
            text_for_step = step.get("text") or step.get("prompt") or action
            logger.info(f"Executing step '{step_id}': skill={skill_name}, action={action}")

            step_output = {
                "step_id": step_id,
                "skill": skill_name,
                "action": action,
                "status": "completed",
            }

            if skill_router is not None:
                try:
                    res = await skill_router.execute(
                        skill_name,
                        text_for_step,
                        {"source": "workflow", "workflow": name},
                    )
                    step_output["result"] = res
                except Exception as e:
                    step_output["status"] = "failed"
                    step_output["error"] = str(e)

            results.append(step_output)

        overall_status = (
            "completed" if all(r["status"] != "failed" for r in results) else "failed"
        )
        return {
            "status": overall_status,
            "workflow": name,
            "total_steps": len(steps),
            "steps": results,
        }
