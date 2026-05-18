"""
Planner Engine — High-level orchestration for goal decomposition, progress tracking, and replanning.
Wraps PlannerDB with business logic and auto-completion detection.
"""

from typing import Any

from planner_db import PlannerDB


class PlannerEngine:
    """Task graph engine with dependency-aware execution and auto-replanning."""

    def __init__(self, db_path: str | None = None):
        self.db = PlannerDB(db_path)

    # ── Goal Management ──────────────────────────────────────────────────

    def create_goal(self, title: str, description: str = "") -> dict[str, Any]:
        goal_id = self.db.create_goal(title, description)
        return {"goal_id": goal_id, "title": title, "status": "pending"}

    def list_goals(self, status: str | None = None) -> list[dict[str, Any]]:
        goals = self.db.list_goals(status)
        result = []
        for g in goals:
            tasks = self.db.get_tasks(g["id"])
            total = len(tasks)
            done = sum(1 for t in tasks if t["status"] == "completed")
            failed = sum(1 for t in tasks if t["status"] == "failed")
            result.append(
                {
                    "goal_id": g["id"],
                    "title": g["title"],
                    "status": g["status"],
                    "progress": f"{done}/{total}" if total > 0 else "no tasks",
                    "failed": failed,
                    "created_at": g["created_at"],
                }
            )
        return result

    # ── Task Decomposition ───────────────────────────────────────────────

    def add_tasks(self, goal_id: int, tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """Add tasks to a goal.

        Each task dict should have:
            - title (str, required)
            - description (str, optional)
            - depends_on (list[int], optional) — task IDs this depends on
            - order_index (int, optional) — execution priority
        """
        goal = self.db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal {goal_id} not found"}

        # Validate dependency references won't create impossible deps
        existing_tasks = self.db.get_tasks(goal_id)
        {t["id"] for t in existing_tasks}

        task_ids = self.db.add_tasks(goal_id, tasks)
        return {
            "goal_id": goal_id,
            "task_ids": task_ids,
            "count": len(task_ids),
        }

    # ── Execution Flow ───────────────────────────────────────────────────

    def get_next_task(self, goal_id: int) -> dict[str, Any]:
        """Get the next task that's ready to execute (all deps met)."""
        goal = self.db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal {goal_id} not found"}
        if goal["status"] in ("completed", "failed"):
            return {
                "message": f"Goal is already {goal['status']}",
                "goal_status": goal["status"],
            }

        task = self.db.get_next_task(goal_id)
        if task:
            return {
                "task_id": task["id"],
                "title": task["title"],
                "description": task["description"],
                "order_index": task["order_index"],
            }

        # No pending tasks — check if all are done
        tasks = self.db.get_tasks(goal_id)
        all_terminal = all(
            t["status"] in ("completed", "failed", "skipped") for t in tasks
        )
        if all_terminal and tasks:
            any_failed = any(t["status"] == "failed" for t in tasks)
            new_status = "failed" if any_failed else "completed"
            self.db.update_goal_status(goal_id, new_status)
            return {
                "message": f"All tasks finished. Goal marked as {new_status}.",
                "goal_status": new_status,
            }

        return {"message": "No tasks are ready yet (dependencies not met)"}

    def update_task_status(
        self, task_id: int, status: str, result: str = "", error: str = ""
    ) -> dict[str, Any]:
        """Update a task's status and handle cascading effects."""
        valid = ("running", "completed", "failed", "skipped")
        if status not in valid:
            return {"error": f"Invalid status '{status}'. Must be one of: {valid}"}

        task = self.db.get_task(task_id)
        if not task:
            return {"error": f"Task {task_id} not found"}

        self.db.update_task_status(task_id, status, result, error)

        response = {"task_id": task_id, "status": status}

        # On failure, skip all dependents
        if status == "failed":
            self.db.skip_dependents(task["goal_id"], task_id)
            response["note"] = "Dependent tasks have been skipped"

        # Check if goal auto-completes
        if status in ("completed", "failed", "skipped"):
            tasks = self.db.get_tasks(task["goal_id"])
            all_terminal = all(
                t["status"] in ("completed", "failed", "skipped") for t in tasks
            )
            if all_terminal and tasks:
                any_failed = any(t["status"] == "failed" for t in tasks)
                new_status = "failed" if any_failed else "completed"
                self.db.update_goal_status(task["goal_id"], new_status)
                response["goal_status"] = new_status

        return response

    # ── Replanning ───────────────────────────────────────────────────────

    def replan(self, goal_id: int, new_tasks: list[dict[str, Any]]) -> dict[str, Any]:
        """Cancel remaining pending tasks and replace with a new plan."""
        goal = self.db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal {goal_id} not found"}

        cancelled = self.db.cancel_pending_tasks(goal_id)
        task_ids = self.db.add_tasks(goal_id, new_tasks)
        self.db.update_goal_status(goal_id, "active")

        return {
            "goal_id": goal_id,
            "cancelled_tasks": cancelled,
            "new_task_ids": task_ids,
            "new_task_count": len(task_ids),
        }

    # ── Status Reporting ─────────────────────────────────────────────────

    def get_goal_status(self, goal_id: int) -> dict[str, Any]:
        """Full progress report for a goal including all tasks."""
        goal = self.db.get_goal(goal_id)
        if not goal:
            return {"error": f"Goal {goal_id} not found"}

        tasks = self.db.get_tasks(goal_id)
        total = len(tasks)
        by_status = {}
        for t in tasks:
            by_status[t["status"]] = by_status.get(t["status"], 0) + 1

        completed = by_status.get("completed", 0)
        progress_pct = round((completed / total) * 100, 1) if total > 0 else 0

        return {
            "goal_id": goal_id,
            "title": goal["title"],
            "description": goal["description"],
            "status": goal["status"],
            "progress": f"{completed}/{total} ({progress_pct}%)",
            "breakdown": by_status,
            "tasks": [
                {
                    "task_id": t["id"],
                    "title": t["title"],
                    "status": t["status"],
                    "result": t["result"],
                    "error": t["error"],
                }
                for t in tasks
            ],
            "created_at": goal["created_at"],
            "updated_at": goal["updated_at"],
        }

    # ── Cleanup ──────────────────────────────────────────────────────────

    def close(self):
        self.db.close()
