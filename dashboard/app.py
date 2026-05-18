"""
Buddy Dashboard — lightweight Flask web server.
Runs on http://localhost:5050 alongside the main assistant.
"""

import logging
import sqlite3
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request

from gui.operator_dashboard import OperatorDashboard

logger = logging.getLogger("buddy.dashboard")

# Will be injected by main.py at startup
_bridge = None
_operator_dashboard = OperatorDashboard()
_reminder_db: Path = Path(__file__).parent.parent / "cache" / "reminders.db"

# Callbacks wired from main.py
_wake_callback = None
_clear_memory_callback = None
_toggle_mic_callback = None
_confirm_callback = None
_chat_callback = None

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True


def init(
    bridge,
    wake_cb=None,
    clear_memory_cb=None,
    toggle_mic_cb=None,
    confirm_cb=None,
    chat_cb=None,
):
    """Called from main.py to inject the DashboardBridge and assistant callbacks."""
    global \
        _bridge, \
        _wake_callback, \
        _clear_memory_callback, \
        _toggle_mic_callback, \
        _confirm_callback, \
        _chat_callback
    _bridge = bridge
    _wake_callback = wake_cb
    _clear_memory_callback = clear_memory_cb
    _toggle_mic_callback = toggle_mic_cb
    _confirm_callback = confirm_cb
    _chat_callback = chat_cb
    logger.info("   🌐 Dashboard bridge connected")


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------


@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------------
# SSE stream
# ------------------------------------------------------------------


@app.route("/stream")
def stream():
    if _bridge is None:
        abort(503, "Bridge not initialised yet")

    def generator():
        yield from _bridge.drain(timeout=20.0)

    return Response(
        generator(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------
# REST API
# ------------------------------------------------------------------


@app.route("/api/status")
def api_status():
    state = _bridge.current_state() if _bridge else "unknown"
    return jsonify({"state": state})


@app.route("/api/operator")
def api_operator():
    """Aggregated operator dashboard data."""
    file_status = _operator_dashboard.get_full_status()
    if not _bridge:
        return jsonify(file_status)
    return jsonify(_merge_operator_payloads(_bridge.operator_summary(), file_status))


@app.route("/api/execution_log")
def api_execution_log():
    """Read recent entries from the JSONL execution log (fallback for CLI/external use)."""
    limit = request.args.get("limit", 20, type=int)
    log_path = Path(__file__).parent.parent / "data" / "execution_log.jsonl"
    if not log_path.exists():
        return jsonify([])
    try:
        import json as _json

        with open(log_path, encoding="utf-8") as f:
            lines = f.readlines()
        entries = []
        for line in lines[-limit:]:
            line = line.strip()
            if line:
                entries.append(_json.loads(line))
        return jsonify(entries)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/reminders")
def api_reminders():
    rows = _get_reminders()
    return jsonify(rows)


@app.route("/api/wake", methods=["POST"])
def api_wake():
    """Trigger the assistant to wake (start listening)."""
    if _wake_callback:
        try:
            _wake_callback()
        except Exception as e:
            logger.error(f"Wake callback failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/companion/wake", methods=["POST"])
def api_companion_wake():
    """Trigger click-to-talk from an external companion surface."""
    state = _current_companion_state()
    if state in {"LISTENING", "PROCESSING", "SPEAKING"}:
        return jsonify(
            {"accepted": False, "reason": "assistant_busy", "state": state}
        ), 409

    if not _wake_callback:
        return jsonify(
            {"accepted": False, "reason": "wake_unavailable", "state": state}
        ), 503

    if _wake_callback:
        try:
            _wake_callback()
        except Exception as e:
            logger.error(f"Companion wake callback failed: {e}")
            return jsonify({"accepted": False, "error": str(e), "state": state}), 500

    return jsonify({"accepted": True, "state": "LISTENING"})


@app.route("/api/companion/state")
def api_companion_state():
    """Return current assistant state for companion startup/reconnect."""
    return jsonify(
        {
            "state": _current_companion_state(),
            "wake_word_enabled": _wake_callback is not None,
            "timestamp": datetime.now().isoformat(),
        }
    )


@app.route("/api/clear_memory", methods=["POST"])
def api_clear_memory():
    """Clear conversation memory."""
    if _clear_memory_callback:
        try:
            _clear_memory_callback()
        except Exception as e:
            logger.error(f"Clear memory callback failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/toggle_mic", methods=["POST"])
def api_toggle_mic():
    """Toggle the microphone on/off."""
    if _toggle_mic_callback:
        try:
            _toggle_mic_callback()
        except Exception as e:
            logger.error(f"Toggle mic callback failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/confirm", methods=["POST"])
def api_confirm():
    """Handle tool confirmation (approve/deny)."""
    data = request.get_json() or {}
    tool_name = data.get("tool_name", "")
    outcome = data.get("outcome", "denied")
    if _confirm_callback:
        try:
            _confirm_callback(tool_name, outcome)
        except Exception as e:
            logger.error(f"Confirm callback failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/chat", methods=["POST"])
def api_chat():
    """Submit a typed chat prompt through the assistant pipeline."""
    if not _chat_callback:
        return jsonify({"ok": False, "error": "Chat callback unavailable"}), 503

    data = request.get_json() or {}
    message = str(data.get("message", "")).strip()
    speak = bool(data.get("speak", False))

    if not message:
        return jsonify({"ok": False, "error": "Message is required"}), 400

    try:
        response = _chat_callback(message, speak=speak)
        return jsonify({"ok": True, "response": response})
    except TimeoutError:
        logger.error("Chat callback timed out")
        return jsonify({"ok": False, "error": "Assistant timed out"}), 504
    except Exception as e:
        logger.error(f"Chat callback failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reminder/<rid>/cancel", methods=["POST"])
def api_cancel_reminder(rid: str):
    try:
        with sqlite3.connect(str(_reminder_db)) as conn:
            conn.execute(
                "UPDATE reminders SET status = 'cancelled' WHERE id = ? AND status = 'pending'",
                (rid,),
            )
        return jsonify({"ok": True})
    except Exception as e:
        logger.error(f"Cancel reminder failed: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _get_reminders():
    if not _reminder_db.exists():
        return []
    try:
        with sqlite3.connect(str(_reminder_db)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.execute(
                "SELECT id, message, trigger_time, cron_expr, status, created_at "
                "FROM reminders WHERE status = 'pending' ORDER BY trigger_time ASC"
            )
            return [dict(r) for r in cursor.fetchall()]
    except Exception as e:
        logger.error(f"Failed to fetch reminders: {e}")
        return []


def _current_companion_state() -> str:
    if not _bridge:
        return "UNKNOWN"
    try:
        return str(_bridge.current_state()).upper()
    except Exception:
        return "UNKNOWN"


def _merge_operator_payloads(bridge_status: dict, file_status: dict) -> dict:
    """Merge live in-memory bridge data with persisted operator snapshots."""
    merged = dict(file_status or {})
    bridge_status = bridge_status or {}

    merged["state"] = bridge_status.get("state", merged.get("state", "unknown"))
    merged["timestamp"] = bridge_status.get("timestamp", merged.get("timestamp"))

    file_health = dict(file_status.get("subsystem_health", {}) if file_status else {})
    file_health.update(bridge_status.get("subsystem_health", {}))
    merged["subsystem_health"] = file_health

    merged["recent_tool_events"] = bridge_status.get("recent_tool_events", [])

    recent_actions = list(file_status.get("recent_actions", []) if file_status else [])
    bridge_events = bridge_status.get("recent_tool_events", [])
    live_actions = [
        {
            "tool_name": event.get("tool_name", "unknown"),
            "duration_ms": event.get("duration_ms", 0),
            "result_summary": event.get("summary", event.get("dry_run", "")),
            "status": event.get("kind", event.get("action", "unknown")),
            "source": "bridge",
        }
        for event in bridge_events
        if event.get("tool_name")
    ]
    merged["recent_actions"] = (live_actions + recent_actions)[:10]

    merged["active_tasks"] = bridge_status.get("active_tasks", {})
    merged["task_state"] = file_status.get("task_state") if file_status else None
    if not merged["task_state"] and merged["active_tasks"]:
        merged["task_state"] = {
            "tasks": {
                task_id: {
                    "goal": task.get("goal", ""),
                    "state": task.get("action", "unknown"),
                    "steps": [],
                }
                for task_id, task in merged["active_tasks"].items()
            }
        }

    live_failures = [
        {
            "tool_name": event.get("tool_name", "unknown"),
            "error": event.get("error", event.get("summary", "tool failure")),
            "duration_ms": event.get("duration_ms", 0),
            "timestamp": event.get("timestamp"),
            "source": "bridge",
        }
        for event in bridge_events
        if event.get("kind") == "failed"
    ]
    merged["tool_failures"] = (
        live_failures + (file_status.get("tool_failures", []) if file_status else [])
    )[:10]

    merged["confirmation_events"] = [
        {
            "tool_name": event.get("tool_name", "unknown"),
            "action": event.get("action", event.get("kind", "unknown")),
            "dry_run": event.get("dry_run", ""),
            "timestamp": event.get("timestamp"),
        }
        for event in bridge_events
        if event.get("kind") == "confirmation"
        or event.get("action") in {"requested", "approved", "denied"}
    ][:10]

    api_stats = dict(file_status.get("api_stats", {}) if file_status else {})
    api_stats.update(_compute_live_api_metrics(bridge_events))
    merged["api_stats"] = api_stats

    authority_audit = _operator_dashboard.get_authority_audit(25)
    merged["authority_audit"] = authority_audit
    merged["authority_summary"] = _compute_authority_summary(authority_audit)
    merged["operator_metrics"] = _compute_operator_metrics(
        api_stats, merged["tool_failures"], merged["confirmation_events"]
    )
    return merged


def _compute_live_api_metrics(bridge_events: list) -> dict:
    """Compute low-latency metrics from live bridge events."""
    events = bridge_events or []
    finished = [e for e in events if e.get("kind") == "finished"]
    failed = [e for e in events if e.get("kind") == "failed"]
    confirmations = [e for e in events if e.get("kind") == "confirmation"]

    avg_latency = 0
    if finished:
        avg_latency = round(
            sum(int(e.get("duration_ms", 0) or 0) for e in finished) / len(finished)
        )

    by_tool = {}
    for event in events:
        tool = event.get("tool_name")
        if tool:
            by_tool[tool] = by_tool.get(tool, 0) + 1

    return {
        "live_recent_calls": len(events),
        "live_recent_success": len(finished),
        "live_recent_failures": len(failed),
        "live_recent_confirmations": len(confirmations),
        "live_recent_avg_latency_ms": avg_latency,
        "live_top_tools": dict(sorted(by_tool.items(), key=lambda item: -item[1])[:5]),
    }


def _compute_authority_summary(entries: list) -> dict:
    """Roll up authority audit rows into quick counters."""
    rows = entries or []
    approved = sum(1 for row in rows if int(row.get("was_approved", 0) or 0) == 1)
    blocked = sum(
        1 for row in rows if str(row.get("action_outcome", "")).lower() == "blocked"
    )
    denied = sum(
        1
        for row in rows
        if int(row.get("was_approved", 0) or 0) == 0
        and str(row.get("action_outcome", "")).lower() != "blocked"
    )
    high_risk = sum(1 for row in rows if int(row.get("risk_level", 0) or 0) >= 3)
    return {
        "approved": approved,
        "denied": denied,
        "blocked": blocked,
        "high_risk_events": high_risk,
    }


def _compute_operator_metrics(
    api_stats: dict, tool_failures: list, confirmations: list
) -> dict:
    """Compose top-level operator metrics used by dashboard cards."""
    stats = api_stats or {}
    total_calls = int(stats.get("total_calls", 0) or 0)
    failure_rate = float(stats.get("failure_rate", 0.0) or 0.0)
    return {
        "total_calls": total_calls,
        "failure_rate": round(failure_rate, 3),
        "recent_failures": len(tool_failures or []),
        "recent_confirmations": len(confirmations or []),
        "avg_latency_ms": int(stats.get("avg_latency_ms", 0) or 0),
        "live_recent_avg_latency_ms": int(
            stats.get("live_recent_avg_latency_ms", 0) or 0
        ),
    }


def run_server(host: str = "127.0.0.1", port: int = 5050):
    """Start Flask in threaded mode (called from a daemon thread)."""
    import logging as _logging

    _logging.getLogger("werkzeug").setLevel(_logging.WARNING)
    app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False)
