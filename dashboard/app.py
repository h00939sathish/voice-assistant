"""
Buddy Dashboard — lightweight Flask web server.
Runs on http://localhost:5050 alongside the main assistant.
Serves live data only: panels without a live source are removed, not faked.
"""

import json
import logging
import secrets
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from flask import Flask, Response, abort, jsonify, render_template, request

from config import USER_NAME, get_api_token
from gui.operator_dashboard import OperatorDashboard

logger = logging.getLogger("buddy.dashboard")

_bridge = None
# Live TaskExecutor (object or zero-arg callable returning it — callable form
# supports executors that are created asynchronously after startup).
_task_executor_source = None
# Live LLMRouter — source of provider health-check results.
_llm_router = None

_operator_dashboard = OperatorDashboard()
_reminder_db: Path = Path(__file__).parent.parent / "cache" / "reminders.db"

_wake_callback = None
_clear_memory_callback = None
_toggle_mic_callback = None
_confirm_callback = None
_chat_callback = None

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True

# Telemetry
from dashboard.telemetry import get_telemetry, TelemetryService
_telemetry = get_telemetry()

# Token auth: everything requires X-Buddy-Token except OPTIONS preflight,
# GET /api/health, and the browser bootstrap surface ("/" + its static
# assets) — the index route is what delivers the token to the browser JS.
# All data/action APIs remain fully gated. The two SSE GET endpoints
# additionally accept ?token= because EventSource cannot set headers.
_SSE_QUERY_TOKEN_PATHS = {"/stream", "/api/metrics/stream"}
_HEALTH_PATH = "/api/health"


@app.before_request
def _require_token():
    if request.method == "OPTIONS":
        return None
    if request.path == _HEALTH_PATH:
        return None
    if request.path == "/" or request.endpoint == "static":
        return None
    provided = request.headers.get("X-Buddy-Token", "")
    if not provided and request.path in _SSE_QUERY_TOKEN_PATHS:
        provided = request.args.get("token", "")
    expected = get_api_token()
    if not provided or not secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        return jsonify({"ok": False, "error": "Invalid or missing API token"}), 401
    return None


# ------------------------------------------------------------------
# Live-state helpers
# ------------------------------------------------------------------

def _get_task_executor():
    if _task_executor_source is None:
        return None
    try:
        return _task_executor_source() if callable(_task_executor_source) \
            else _task_executor_source
    except Exception as e:
        logger.warning(f"TaskExecutor provider failed: {e}")
        return None


def _active_task():
    executor = _get_task_executor()
    if executor is None:
        return None
    try:
        return executor.get_active_task()
    except Exception as e:
        logger.warning(f"Failed to read active task: {e}")
        return None


def _live_tasks() -> list:
    executor = _get_task_executor()
    if executor is None:
        return []
    try:
        tasks = executor.get_all_tasks()
    except Exception as e:
        logger.warning(f"Failed to read tasks: {e}")
        return []
    serialised = []
    for task in tasks:
        try:
            serialised.append(task.to_dict())
        except Exception:
            continue
    return serialised


def _routing_rows() -> list:
    if _llm_router is None:
        return []
    try:
        health = _llm_router.get_provider_health()
    except Exception as e:
        logger.warning(f"Failed to read provider health: {e}")
        return []
    rows = []
    for entry in health or []:
        if not isinstance(entry, dict):
            continue
        rows.append({
            "provider": str(entry.get("provider", "")),
            "status": "online" if entry.get("ok") else "offline",
            "model": str(entry.get("model", "") or ""),
        })
    return rows


# ------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html", buddy_token=get_api_token())


@app.route("/api/health")
def api_health():
    """Unauthenticated liveness probe (the only route exempt from token auth)."""
    return jsonify({"status": "ok"})


# ------------------------------------------------------------------
# SSE streams
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


@app.route("/api/metrics/stream")
def api_metrics_stream():
    """SSE endpoint for real system telemetry — pushes every 3 seconds."""

    def generate():
        while True:
            m = _telemetry.collect()
            payload = json.dumps({
                "type": "metrics",
                "data": {
                    "cpu": m.cpu,
                    "ram": m.ram,
                    "gpu": m.gpu,
                    "vram": m.vram,
                    "gpu_temp": m.gpu_temp,
                    "gpu_power": m.gpu_power,
                    "gpu_fan": m.gpu_fan,
                    "gpu_name": m.gpu_name,
                    "vram_used": m.vram_used,
                    "vram_total": m.vram_total,
                    "disk": m.disk,
                    "network": m.network,
                    "cpu_temp": m.cpu_temp,
                    "uptime": m.uptime,
                    "processes": m.processes,
                }
            })
            yield f"data: {payload}\n\n"
            time.sleep(3)

    return Response(
        generate(),
        mimetype="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ------------------------------------------------------------------
# REST API
# ------------------------------------------------------------------

@app.route("/api/status")
def api_status():
    state = _bridge.current_state() if _bridge else "unknown"
    return jsonify({
        "state": state,
        "tasks": _live_tasks(),
    })


@app.route("/api/objective")
def api_objective():
    active = _active_task()
    return jsonify({"objective": active.goal if active else None})


@app.route("/api/tasks")
def api_tasks():
    return jsonify(_live_tasks())


@app.route("/api/model-routing")
def api_model_routing():
    return jsonify(_routing_rows())


@app.route("/api/memory")
def api_memory():
    return jsonify({
        "name": USER_NAME,
        "projects": [],
        "recent": [],
        "pinned": [],
    })


@app.route("/api/agent/log")
def api_agent_log():
    if not _bridge:
        return jsonify([])
    try:
        events = _bridge.recent_tool_events(20)
    except Exception as e:
        logger.warning(f"Failed to read tool events: {e}")
        return jsonify([])
    entries = []
    for event in events or []:
        if not isinstance(event, dict) or not event.get("tool_name"):
            continue
        message = f"{event['tool_name']} {event.get('kind', 'event')}"
        if event.get("summary"):
            message += f": {event['summary']}"
        elif event.get("error"):
            message += f": {event['error']}"
        entries.append({"timestamp": event.get("timestamp"), "message": message})
    return jsonify(entries)


@app.route("/api/system/info")
def api_system_info():
    return jsonify(_telemetry.get_system_info())


# ------------------------------------------------------------------
# Live2D / pet abstraction
# ------------------------------------------------------------------

@app.route("/jarvis/state")
def jarvis_state():
    """Unified state API for Live2D pets, Desktop Waifu, etc."""
    state = _bridge.current_state() if _bridge else "unknown"
    active = _active_task()
    progress = 0
    step = ""
    if active:
        steps = getattr(active, "steps", None) or []
        index = getattr(active, "current_step_index", 0) or 0
        if steps:
            progress = round(min(index, len(steps)) / len(steps) * 100)
            if index < len(steps):
                step = getattr(steps[index], "description", "") or ""
    return jsonify({
        "state": state.upper() if state != "unknown" else "UNKNOWN",
        "objective": getattr(active, "goal", "") if active else "",
        "progress": progress,
        "step": step,
        "timestamp": datetime.now().isoformat(),
    })


# ------------------------------------------------------------------
# Operator dashboard
# ------------------------------------------------------------------

@app.route("/api/operator")
def api_operator():
    file_status = _operator_dashboard.get_full_status()
    if not _bridge:
        return jsonify(file_status)
    return jsonify(_merge_operator_payloads(_bridge.operator_summary(), file_status))


@app.route("/api/execution_log")
def api_execution_log():
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


# ------------------------------------------------------------------
# Action endpoints
# ------------------------------------------------------------------

@app.route("/api/wake", methods=["POST"])
def api_wake():
    if _wake_callback:
        try:
            _wake_callback()
        except Exception as e:
            logger.error(f"Wake callback failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/companion/wake", methods=["POST"])
def api_companion_wake():
    state = _current_companion_state()
    if state in {"LISTENING", "PROCESSING", "SPEAKING"}:
        return jsonify({"accepted": False, "reason": "assistant_busy", "state": state}), 409
    if not _wake_callback:
        return jsonify({"accepted": False, "reason": "wake_unavailable", "state": state}), 503
    if _wake_callback:
        try:
            _wake_callback()
        except Exception as e:
            logger.error(f"Companion wake callback failed: {e}")
            return jsonify({"accepted": False, "error": str(e), "state": state}), 500
    return jsonify({"accepted": True, "state": "LISTENING"})


@app.route("/api/companion/state")
def api_companion_state():
    return jsonify({
        "state": _current_companion_state(),
        "wake_word_enabled": _wake_callback is not None,
        "timestamp": datetime.now().isoformat(),
    })


@app.route("/api/clear_memory", methods=["POST"])
def api_clear_memory():
    if _clear_memory_callback:
        try:
            _clear_memory_callback()
        except Exception as e:
            logger.error(f"Clear memory callback failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/toggle_mic", methods=["POST"])
def api_toggle_mic():
    if _toggle_mic_callback:
        try:
            _toggle_mic_callback()
        except Exception as e:
            logger.error(f"Toggle mic callback failed: {e}")
            return jsonify({"ok": False, "error": str(e)}), 500
    return jsonify({"ok": True})


@app.route("/api/confirm", methods=["POST"])
def api_confirm():
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
        return jsonify({"ok": False, "error": "Assistant timed out"}), 504
    except Exception as e:
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/reminders")
def api_reminders():
    rows = _get_reminders()
    return jsonify(rows)


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

def init(bridge, wake_cb=None, clear_memory_cb=None, toggle_mic_cb=None,
         confirm_cb=None, chat_cb=None, task_executor=None, llm_router=None):
    global _bridge, _wake_callback, _clear_memory_callback, _toggle_mic_callback
    global _confirm_callback, _chat_callback
    global _task_executor_source, _llm_router
    _bridge = bridge
    _wake_callback = wake_cb
    _clear_memory_callback = clear_memory_cb
    _toggle_mic_callback = toggle_mic_cb
    _confirm_callback = confirm_cb
    _chat_callback = chat_cb
    # Live references for real-data endpoints. `task_executor` may be the
    # executor itself or a zero-arg callable returning it (the executor is
    # created asynchronously during assistant startup).
    _task_executor_source = task_executor
    _llm_router = llm_router
    logger.info("   Dashboard bridge connected")


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
        {"tool_name": event.get("tool_name", "unknown"),
         "duration_ms": event.get("duration_ms", 0),
         "result_summary": event.get("summary", event.get("dry_run", "")),
         "status": event.get("kind", event.get("action", "unknown")),
         "source": "bridge"}
        for event in bridge_events if event.get("tool_name")
    ]
    merged["recent_actions"] = (live_actions + recent_actions)[:10]
    merged["active_tasks"] = bridge_status.get("active_tasks", {})
    merged["task_state"] = file_status.get("task_state") if file_status else None
    if not merged["task_state"] and merged["active_tasks"]:
        merged["task_state"] = {
            "tasks": {task_id: {"goal": task.get("goal", ""),
                                "state": task.get("action", "unknown"), "steps": []}
                      for task_id, task in merged["active_tasks"].items()}
        }
    live_failures = [
        {"tool_name": event.get("tool_name", "unknown"),
         "error": event.get("error", event.get("summary", "tool failure")),
         "duration_ms": event.get("duration_ms", 0),
         "timestamp": event.get("timestamp"), "source": "bridge"}
        for event in bridge_events if event.get("kind") == "failed"
    ]
    merged["tool_failures"] = (live_failures + (file_status.get("tool_failures", []) if file_status else []))[:10]
    merged["confirmation_events"] = [
        {"tool_name": event.get("tool_name", "unknown"),
         "action": event.get("action", event.get("kind", "unknown")),
         "dry_run": event.get("dry_run", ""), "timestamp": event.get("timestamp")}
        for event in bridge_events
        if event.get("kind") == "confirmation" or event.get("action") in {"requested", "approved", "denied"}
    ][:10]
    api_stats = dict(file_status.get("api_stats", {}) if file_status else {})
    api_stats.update(_compute_live_api_metrics(bridge_events))
    merged["api_stats"] = api_stats
    authority_audit = _operator_dashboard.get_authority_audit(25)
    merged["authority_audit"] = authority_audit
    merged["authority_summary"] = _compute_authority_summary(authority_audit)
    merged["operator_metrics"] = _compute_operator_metrics(api_stats, merged["tool_failures"], merged["confirmation_events"])
    return merged


def _compute_live_api_metrics(bridge_events: list) -> dict:
    events = bridge_events or []
    finished = [e for e in events if e.get("kind") == "finished"]
    failed = [e for e in events if e.get("kind") == "failed"]
    confirmations = [e for e in events if e.get("kind") == "confirmation"]
    avg_latency = 0
    if finished:
        avg_latency = round(sum(int(e.get("duration_ms", 0) or 0) for e in finished) / len(finished))
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
    rows = entries or []
    approved = sum(1 for row in rows if int(row.get("was_approved", 0) or 0) == 1)
    blocked = sum(1 for row in rows if str(row.get("action_outcome", "")).lower() == "blocked")
    denied = sum(1 for row in rows if int(row.get("was_approved", 0) or 0) == 0 and str(row.get("action_outcome", "")).lower() != "blocked")
    high_risk = sum(1 for row in rows if int(row.get("risk_level", 0) or 0) >= 3)
    return {"approved": approved, "denied": denied, "blocked": blocked, "high_risk_events": high_risk}


def _compute_operator_metrics(api_stats: dict, tool_failures: list, confirmations: list) -> dict:
    stats = api_stats or {}
    total_calls = int(stats.get("total_calls", 0) or 0)
    failure_rate = float(stats.get("failure_rate", 0.0) or 0.0)
    return {
        "total_calls": total_calls,
        "failure_rate": round(failure_rate, 3),
        "recent_failures": len(tool_failures or []),
        "recent_confirmations": len(confirmations or []),
        "avg_latency_ms": int(stats.get("avg_latency_ms", 0) or 0),
        "live_recent_avg_latency_ms": int(stats.get("live_recent_avg_latency_ms", 0) or 0),
    }


def run_server(host: str = "127.0.0.1", port: int = 5050):
    import logging as _logging
    _logging.getLogger("werkzeug").setLevel(_logging.WARNING)
    app.run(host=host, port=port, threaded=True, use_reloader=False, debug=False)
