"""
Tests for PlannerEngine — unit tests for task decomposition, dependency resolution,
auto-completion, failure cascading, and replanning.

Run:
    cd /media/sathish/Windows/Users/h0093/Documents/new
    python -m pytest tests/test_planner_engine.py -v
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(
    0,
    os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "mcp-tools",
        "planner-mcp",
    ),
)

from planner_engine import PlannerEngine


@pytest.fixture
def engine(tmp_path):
    """Fresh PlannerEngine with isolated temp DB for each test."""
    db_path = str(tmp_path / "test_planner.db")
    eng = PlannerEngine(db_path=db_path)
    yield eng
    eng.close()


# ── Goal Lifecycle ───────────────────────────────────────────────────────


class TestGoalLifecycle:
    def test_create_goal(self, engine):
        result = engine.create_goal("Test Goal", "A test description")
        assert "goal_id" in result
        assert result["title"] == "Test Goal"
        assert result["status"] == "pending"

    def test_list_goals_empty(self, engine):
        goals = engine.list_goals()
        assert goals == []

    def test_list_goals_with_filter(self, engine):
        engine.create_goal("Goal A")
        engine.create_goal("Goal B")
        # Both start as 'pending'
        pending = engine.list_goals(status="pending")
        assert len(pending) == 2
        active = engine.list_goals(status="active")
        assert len(active) == 0

    def test_goal_auto_completes_on_all_tasks_done(self, engine):
        result = engine.create_goal("Auto-complete Test")
        goal_id = result["goal_id"]

        engine.add_tasks(
            goal_id,
            [
                {"title": "Step 1"},
                {"title": "Step 2"},
            ],
        )

        # Complete both tasks
        t1 = engine.get_next_task(goal_id)
        engine.update_task_status(t1["task_id"], "completed", result="Done")
        t2 = engine.get_next_task(goal_id)
        engine.update_task_status(t2["task_id"], "completed", result="Done")

        # Goal should auto-complete
        status = engine.get_goal_status(goal_id)
        assert status["status"] == "completed"

    def test_goal_auto_fails_when_task_fails(self, engine):
        result = engine.create_goal("Fail Test")
        goal_id = result["goal_id"]

        engine.add_tasks(goal_id, [{"title": "Only Step"}])

        t = engine.get_next_task(goal_id)
        engine.update_task_status(t["task_id"], "failed", error="Boom")

        status = engine.get_goal_status(goal_id)
        assert status["status"] == "failed"


# ── Dependency Resolution ────────────────────────────────────────────────


class TestDependencyResolution:
    def test_sequential_dependency(self, engine):
        """Task B depends on Task A — B only available after A completes."""
        result = engine.create_goal("Dependency Test")
        goal_id = result["goal_id"]

        add_result = engine.add_tasks(
            goal_id,
            [
                {"title": "Task A"},
            ],
        )
        task_a_id = add_result["task_ids"][0]

        engine.add_tasks(
            goal_id,
            [
                {"title": "Task B", "depends_on": [task_a_id]},
            ],
        )

        # First next task should be A
        next_t = engine.get_next_task(goal_id)
        assert next_t["title"] == "Task A"

        # Complete A
        engine.update_task_status(task_a_id, "completed")

        # Now B should be available
        next_t = engine.get_next_task(goal_id)
        assert next_t["title"] == "Task B"

    def test_parallel_tasks_no_deps(self, engine):
        """Tasks without dependencies are all available."""
        result = engine.create_goal("Parallel Test")
        goal_id = result["goal_id"]

        engine.add_tasks(
            goal_id,
            [
                {"title": "Task A", "order_index": 0},
                {"title": "Task B", "order_index": 1},
                {"title": "Task C", "order_index": 2},
            ],
        )

        # All tasks are available (first by order_index)
        t = engine.get_next_task(goal_id)
        assert t["title"] == "Task A"

    def test_blocked_by_unmet_dependency(self, engine):
        """Task with unmet dep should not be returned."""
        result = engine.create_goal("Blocked test")
        goal_id = result["goal_id"]

        add_result = engine.add_tasks(
            goal_id,
            [
                {"title": "Task A"},
            ],
        )
        task_a_id = add_result["task_ids"][0]

        engine.add_tasks(
            goal_id,
            [
                {"title": "Task B", "depends_on": [task_a_id]},
            ],
        )

        # Start A (but don't complete it)
        engine.update_task_status(task_a_id, "running")

        # B should not be available (A is running, not completed)
        next_t = engine.get_next_task(goal_id)
        assert "message" in next_t  # No tasks ready


# ── Failure Cascading ────────────────────────────────────────────────────


class TestFailureCascading:
    def test_fail_cascades_to_dependents(self, engine):
        """Failing a task skips all dependent tasks."""
        result = engine.create_goal("Cascade Test")
        goal_id = result["goal_id"]

        add_result = engine.add_tasks(
            goal_id,
            [
                {"title": "Task A"},
            ],
        )
        task_a_id = add_result["task_ids"][0]

        engine.add_tasks(
            goal_id,
            [
                {"title": "Task B", "depends_on": [task_a_id]},
                {"title": "Task C", "depends_on": [task_a_id]},
            ],
        )

        # Fail A
        result = engine.update_task_status(task_a_id, "failed", error="Network down")
        assert "Dependent tasks have been skipped" in result.get("note", "")

        # B and C should be skipped
        status = engine.get_goal_status(goal_id)
        task_statuses = {t["title"]: t["status"] for t in status["tasks"]}
        assert task_statuses["Task B"] == "skipped"
        assert task_statuses["Task C"] == "skipped"


# ── Replanning ───────────────────────────────────────────────────────────


class TestReplanning:
    def test_replan_cancels_pending_adds_new(self, engine):
        result = engine.create_goal("Replan Test")
        goal_id = result["goal_id"]

        engine.add_tasks(
            goal_id,
            [
                {"title": "Old Step 1"},
                {"title": "Old Step 2"},
                {"title": "Old Step 3"},
            ],
        )

        # Complete step 1
        t = engine.get_next_task(goal_id)
        engine.update_task_status(t["task_id"], "completed")

        # Replan — should cancel Old Step 2 & 3, add new
        replan_result = engine.replan(
            goal_id,
            [
                {"title": "New Step A"},
                {"title": "New Step B"},
            ],
        )

        assert replan_result["cancelled_tasks"] == 2
        assert replan_result["new_task_count"] == 2

        # Next task should be one of the new ones
        t = engine.get_next_task(goal_id)
        assert t["title"] == "New Step A"

    def test_replan_nonexistent_goal(self, engine):
        result = engine.replan(9999, [{"title": "X"}])
        assert "error" in result


# ── Status Reporting ─────────────────────────────────────────────────────


class TestStatusReporting:
    def test_goal_status_progress(self, engine):
        result = engine.create_goal("Progress Test")
        goal_id = result["goal_id"]

        engine.add_tasks(
            goal_id,
            [
                {"title": "Step 1"},
                {"title": "Step 2"},
                {"title": "Step 3"},
            ],
        )

        # Complete 1 of 3
        t = engine.get_next_task(goal_id)
        engine.update_task_status(t["task_id"], "completed")

        status = engine.get_goal_status(goal_id)
        assert "1/3" in status["progress"]
        assert status["breakdown"]["completed"] == 1
        assert status["breakdown"]["pending"] == 2

    def test_nonexistent_goal_returns_error(self, engine):
        status = engine.get_goal_status(9999)
        assert "error" in status


# ── Edge Cases ───────────────────────────────────────────────────────────


class TestEdgeCases:
    def test_empty_task_list(self, engine):
        result = engine.create_goal("Empty Goal")
        goal_id = result["goal_id"]

        add_result = engine.add_tasks(goal_id, [])
        assert add_result["count"] == 0

    def test_multiple_independent_goals(self, engine):
        g1 = engine.create_goal("Goal 1")
        g2 = engine.create_goal("Goal 2")

        engine.add_tasks(g1["goal_id"], [{"title": "G1 Step"}])
        engine.add_tasks(g2["goal_id"], [{"title": "G2 Step"}])

        t1 = engine.get_next_task(g1["goal_id"])
        t2 = engine.get_next_task(g2["goal_id"])

        assert t1["title"] == "G1 Step"
        assert t2["title"] == "G2 Step"

    def test_invalid_status_rejected(self, engine):
        result = engine.create_goal("Validation Test")
        goal_id = result["goal_id"]
        engine.add_tasks(goal_id, [{"title": "Step"}])
        t = engine.get_next_task(goal_id)

        result = engine.update_task_status(t["task_id"], "invalid_status")
        assert "error" in result

    def test_nonexistent_task_update(self, engine):
        result = engine.update_task_status(99999, "completed")
        assert "error" in result
