# Buddy Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Buddy from "demo-data face on an over-engineered skeleton" into an honest, secure, streaming voice assistant.

**Architecture:** Windows-only local voice assistant (Python 3.11 target, currently runs on a 3.14 venv): openWakeWord → faster-whisper STT → LLMRouter (8 providers w/ fallback) → skills/MCP tools → streaming TTS cascade. FastAPI control plane on :8765, Flask dashboard on :5055. Authority gate guards tool execution.

**Tech Stack:** Python, FastAPI/uvicorn/SSE, Flask, SQLite (+sqlite-vec), faster-whisper, openWakeWord, edge-tts/Piper/pyttsx3, PyQt6 orb overlay, MCP stdio servers, pytest + ruff.

## Global Constraints

- Target Python **3.11** compatibility (no 3.12+-only syntax/APIs); CI pins 3.11. Current venv is 3.14 — tests run there until Task 13 rebuilds it.
- Test command: `.\venv\Scripts\python.exe -m pytest <paths> -v` from repo root. Full suite: `.\venv\Scripts\python.exe -m pytest -q` (allow up to 10 min).
- Lint: `.\venv\Scripts\python.exe -m ruff check assistant dashboard tests` must stay clean; line-length 88.
- NEVER commit `.env`, `data/*.db`, logs, models, or `AionUi/` / vendored trees. `.gitignore` covers these — do not weaken it.
- No new dependencies without justification in the task report; prefer stdlib.
- GitNexus MCP is not wired into this session: each implementer performs a **manual impact check** instead — before editing a symbol, `grep` for its callers, list them in the task report ("Impact: callers=X,Y,Z; risk=LOW/HIGH"). If HIGH (broad callers), note blast radius explicitly.
- Every task: failing test first → minimal implementation → green → `git commit` with the given message → self-review diff.
- Do not refactor beyond the task spec (no opportunistic renames/moves).

---

### Task 1: Fix workflow engine silent no-op

**Files:**
- Modify: `assistant/workflow_engine.py` (execute_workflow, ~lines 52–90)
- Modify: `assistant/skill_router.py` (add public execute method near `_execute_skill`, ~line 187)
- Test: `tests/test_workflow_engine.py`

**Interfaces:**
- Produces: `SkillRouter.execute(self, name: str, text: str, context: dict | None = None) -> str` — public async wrapper that validates the skill exists and delegates to `_execute_skill`.
- Consumes: existing `_execute_skill(name, text, context)`; existing WorkflowEngine.load/execute_workflow API unchanged.

- [ ] **Step 1: Read current behavior.** Read `assistant/workflow_engine.py`, `assistant/skill_router.py`, `workflows/good_morning.yaml`, and `tests/test_workflow_engine.py`. Confirm the bug: `hasattr(skill_router, "execute_skill")` is always False (only `_execute_skill` exists), so steps are marked completed without executing.

- [ ] **Step 2: Write failing tests.** In `tests/test_workflow_engine.py` add:

```python
async def test_execute_workflow_runs_skill_through_router(loaded_router, tmp_path):
    wf_file = tmp_path / "wf.yaml"
    wf_file.write_text(
        "name: test_wf\nsteps:\n  - skill: time\n    text: what time is it\n"
    )
    loaded_router._execute_skill = AsyncMock(return_value="ok")
    engine = WorkflowEngine(base_dir=tmp_path)
    result = await engine.execute_workflow("test_wf", skill_router=loaded_router)
    assert result["status"] == "completed"
    loaded_router._execute_skill.assert_awaited_once_with(
        "time", "what time is it", ANY
    )
    assert result["steps"][0]["status"] == "completed"

async def test_execute_workflow_marks_failed_step_failed(tmp_path):
    class Boom:
        async def execute(self, name, text, context=None):
            raise RuntimeError("boom")
    wf_file = tmp_path / "bad.yaml"
    wf_file.write_text("name: bad\nsteps:\n  - skill: time\n    text: x\n")
    engine = WorkflowEngine(base_dir=tmp_path)
    result = await engine.execute_workflow("bad", skill_router=Boom())
    assert result["steps"][0]["status"] == "failed"
    assert "boom" in result["steps"][0]["error"]
```

Adjust fixture names to whatever exists; if `loaded_router` differs, construct minimal router stub. Match the file's existing conventions.

- [ ] **Step 3: Run tests, verify FAIL** (`pytest tests/test_workflow_engine.py -v`) — new tests fail because steps never execute.

- [ ] **Step 4: Implement.**
  In `skill_router.py` add public method delegating through the same path used by `handle()`:

```python
async def execute(self, name: str, text: str, context: dict | None = None) -> str:
    """Public entry point for direct skill invocation (workflows, APIs)."""
    return await self._execute_skill(name, text, context or {})
```

  In `workflow_engine.py`: replace the hasattr block. Call `skill_router.execute(skill_name, text_for_step, {"source": "workflow", "workflow": name})`. Wrap per-step await in try/except; on exception record `{"status": "failed", "error": str(exc)}` and set overall status accordingly; never mark a failed step completed. Map whatever field names the real YAML uses (read `workflows/good_morning.yaml`) — support both `text:` and `prompt:` keys if present.

- [ ] **Step 5: Run tests green** then full file suite `pytest tests/test_workflow_engine.py tests/test_skill_routing.py tests/test_skill_safety_routing.py -v`.

- [ ] **Step 6: Impact note + lint + commit.** grep callers of `execute_skill|_execute_skill`; record in report. `ruff check assistant`. Commit: `fix(workflow): execute steps through SkillRouter.execute instead of silently marking complete`

---

### Task 2: Delete dead dashboard frontends

**Files:**
- Delete: `dashboard/static/app.js`, `dashboard/static/buddy-ws-client.js`

- [ ] **Step 1: Verify zero references**: grep repo for `app.js`, `buddy-ws-client` in `dashboard/**/*.{html,py}` and `assistant/**`. Expected: none.
- [ ] **Step 2:** `git rm dashboard/static/app.js dashboard/static/buddy-ws-client.js`
- [ ] **Step 3: Smoke:** start nothing; just `ruff check dashboard` and confirm templates don't reference deleted files (grep again post-delete).
- [ ] **Step 4: Commit:** `chore(dashboard): remove unreferenced legacy JS frontend`

---

### Task 3: Dashboard shows real data or panels are removed

**Files:**
- Modify: `dashboard/app.py` (~lines 39–91 demo constants; `/api/status`, `/api/objective`, `/api/tasks`, `/api/model-routing`, `/api/memory` handlers)
- Modify: `dashboard/templates/index.html` (~lines 22–50 hardcoded JS mirrors)
- Modify: `config.py` (add `USER_NAME`)
- Modify: `main.py` / `assistant/dashboard_bridge.py` ONLY IF needed to pass live references into the Flask app factory (prefer reading from the bridge/state already available to app.py)
- Test: `tests/test_dashboard_real_data.py` (new)

**Interfaces:**
- Consumes: `TaskExecutor` live state (PENDING/RUNNING/PAUSED/COMPLETED/FAILED tasks incl. descriptions), `LLMRouter` provider health results (names + ok/fail + model ids).
- Produces: `/api/objective` returns `{objective: str|null}`, `/api/tasks` returns current queue from TaskExecutor, `/api/model-routing` returns `[{provider, status, model}]` from last health check, `/api/memory` owner name from `config.USER_NAME`. Removed endpoints return 404.

- [ ] **Step 1: Inventory.** Read `dashboard/app.py` fully; identify how it accesses assistant state today (bridge? globals?). Identify every endpoint backed by hardcoded data vs live. List panels fed by `_objective/_tasks/_agents/_ecosystem/_model_routing`.
- [ ] **Step 2: Failing contract test** `tests/test_dashboard_real_data.py`: build the Flask app with a stub bridge exposing a fake TaskExecutor (one RUNNING task "draft report") and fake provider health `[{"provider":"ollama","ok":True,"model":"qwen3"}]`; assert JSON responses contain those values and NOT the fictional strings `"Ternary Bonsai"`, `"DeepSeek V4 Pro"`, `"railway"`, `"openbb"`, `"Sathish"`. Assert removed panels' routes 404.
- [ ] **Step 3: Red run.**
- [ ] **Step 4: Implement.** Wire handlers to live objects (pass executor/router refs into app factory via existing bridge mechanism — read how `main.py` starts the dashboard thread and follow it). Add `USER_NAME = os.getenv("USER_NAME", "sir")` in config.py; replace hardcodes. DELETE agents/ecosystem panels end-to-end: their `/api/*` handlers, index.html panel components, and CSS blocks unique to them. Update index.html JS literals (lines ~22–50) to fetch from the live endpoints with graceful "—" empty states.
- [ ] **Step 5: Green run + `pytest tests/test_foundational_build.py -v`** (it covers dashboard payload merges — fix any fallout by adapting assertions to live sources, not by reintroducing fakes).
- [ ] **Step 6: Commit:** `feat(dashboard): wire live task/model data, remove fictional panels`

---

### Task 4: Remove vestiges

**Files:**
- Delete: `assistant/llm_cache.py`
- Modify: importers of llm_cache (grep; likely api_server.py or llm_router.py — remove import + usage lines)
- Modify: `assistant/skill_router.py` — remove `_llm_classify` method and its call site branch (dead: always returns None)
- Modify: `requirements.txt` — deduplicate `pystray`, `Pillow`, `aiohttp` (keep single entries)

- [ ] **Step 1: grep `llm_cache|_llm_classify`** — list all references in report.
- [ ] **Step 2:** Remove code + any now-unused imports. If llm_cache usage is functional (not just imported), STOP and report NEEDS_CONTEXT instead of removing.
- [ ] **Step 3:** Dedupe requirements.txt preserving order/comments.
- [ ] **Step 4:** `pytest -q` targeted: `pytest tests/test_skill_routing.py tests/test_skill_safety_routing.py tests/test_api_contract.py -v`; ruff clean.
- [ ] **Step 5: Commit:** `chore: remove stub llm cache, dead classifier, duplicate deps`

---

### Task 5: Docs reality pass

**Files:**
- Modify: `AGENTS.md` — rewrite stale sections: no Flask-SocketIO (FastAPI SSE `/stream`, `/api/metrics/stream`, WS `/ws`), no Tailwind v4/Babel/CDN-React-with-JSX (single-file React via createElement, custom CSS), correct component tree, correct route list (match Task 3 outcomes)
- Modify: `README.md` — architecture diagram + feature bullets match reality (Windows-only, ports 8765/5055, authority gate, MCP client+server)

- [ ] **Step 1:** Diff docs claims vs code; list corrections in report.
- [ ] **Step 2:** Rewrite only false sections; keep structure/tone. No marketing fluff.
- [ ] **Step 3: Commit:** `docs: align AGENTS/README with actual architecture (SSE, no Tailwind/SocketIO)`

---

### Task 6: Token auth on both servers

**Files:**
- Modify: `config.py` (token bootstrap)
- Modify: `assistant/api_server.py` (FastAPI dependency + exemptions)
- Modify: `dashboard/app.py` (before_request + template token injection)
- Modify: `dashboard/templates/index.html` (attach header to fetches)
- Modify: `assistant/dashboard_bridge.py` if it makes HTTP calls to itself/others (attach header)
- Test: `tests/test_token_auth.py` (new)

**Interfaces:**
- config: `def get_api_token() -> str` — returns env `BUDDY_API_TOKEN` or loads/creates `data/api_token` (mode restricted) using `secrets.token_urlsafe(32)`; logs only the path, never the value.
- FastAPI: `require_token` dependency reads header `X-Buddy-Token`, `secrets.compare_digest` against token; applied at router level so ALL routes require it except: `OPTIONS` preflight and `GET /api/health`. Startup guard: if bind host != loopback and env token unset → raise RuntimeError at startup.
- Flask: `@app.before_request` same check (exempt `OPTIONS`, `/api/health`); index.html rendered with `window.__BUDDY_TOKEN__` injected by the route; all JS `fetch()` wrappers attach `X-Buddy-Token`.
- Non-loopback refusal applies to BOTH servers.

- [ ] **Step 1: Failing tests** (`tests/test_token_auth.py`, FastAPI TestClient + Flask test client):
  - 401 without header on `/api/chat` (or any protected GET like `/api/status`)
  - 401 wrong token; 200 correct token
  - `/api/health` exempt
  - Flask: same trio
  - `get_api_token()` creates file once, returns same value on second call
  - non-loopback host + no env token → RuntimeError raised by server factory/main wiring (test the guard function directly)
- [ ] **Step 2: Red run.**
- [ ] **Step 3: Implement** per interfaces above. Constant-time compare only. Never log tokens. Follow each file's existing error-response shape (JSON `{"detail": ...}` for FastAPI, Flask jsonify for 401).
- [ ] **Step 4: Green** + run `pytest tests/test_api_contract.py tests/test_foundational_build.py -v` and fix fallout (update test clients to send the header; add a shared test helper `auth_headers(token)`).
- [ ] **Step 5: Commit:** `feat(security): token-authenticate FastAPI control plane and Flask dashboard`

---

### Task 7: CORS locked to loopback origins

**Files:**
- Modify: `assistant/api_server.py` — add `CORSMiddleware(allow_origins=["http://127.0.0.1:5055","http://127.0.0.1:8765","http://localhost:5055"], allow_credentials=False, allow_methods=["*"], allow_headers=["X-Buddy-Token","Content-Type"])`
- Modify: `dashboard/app.py` — after_request CORS headers with same origin allowlist for its own port
- Test: extend `tests/test_token_auth.py`

- [ ] **Step 1: Failing test:** OPTIONS preflight from disallowed origin lacks `Access-Control-Allow-Origin`; allowed origin present.
- [ ] **Step 2: Implement.** [ ] **Step 3: Green.** [ ] **Step 4: Commit:** `feat(security): restrict CORS to loopback dashboard origins`

---

### Task 8: Remote desktop execution behind forced confirmation

**Files:**
- Modify: `assistant/api_server.py` — locate `/api/desktop/execute` (and any HTTP route invoking CRITICAL-risk tools); route through ToolRunner/authority gate with confirmation transport that **auto-denies when no interactive callback is registered**
- Test: `tests/test_remote_exec_safety.py` (new)

**Interfaces:**
- Consumes: existing ToolRunner statuses (`requires_confirmation`, `blocked`) and authority gate risk classification.
- Produces: HTTP 202 `{status:"requires_confirmation", message}` for HIGH/CRITICAL actions with no human attached; HTTP 403 `{status:"blocked"}` when policy denies; NEVER executes CRITICAL inline.

- [ ] **Step 1: Trace path:** read handler → tool dispatch; identify where confirmations are decided today. Report flow in one paragraph.
- [ ] **Step 2: Failing test:** stub authority policy marking `run_command` CRITICAL → POST payload calling it → assert 202/blocked, assert audit row written (`data/authority_audit.db` or injected tmp db), assert underlying executor NOT called. Second case: LOW-risk action still executes normally.
- [ ] **Step 3: Implement:** force `requires_confirmation` outcome when transport is non-interactive; never auto-approve.
- [ ] **Step 4: Green + foundational suite.** [ ] **Step 5: Commit:** `feat(security): remote desktop/tool execution cannot bypass authority gate confirmation`

---

### Task 9: LLMRouter.stream_chat

**Files:**
- Modify: `assistant/llm_router.py` — add `stream_chat`
- Modify: `assistant/llm_providers.py` — add per-provider `chat_stream` ONLY where SDK natively supports streaming (Ollama, Groq/OpenAI-compatible, Gemini); others reuse non-streaming chat
- Test: `tests/test_stream_chat.py` (new)

**Interfaces:**
- `def stream_chat(self, messages: list[dict], *, tools: list[dict] | None = None) -> AsyncIterator[str]`
- Semantics: resolve provider chain BEFORE first yield (reuse existing health/fallback ordering); iterate providers; on connection/auth error BEFORE any token yielded → next provider; once a token has been yielded, errors propagate (documented, no mid-stream failover). Providers without native streaming: yield whole `chat()` reply as ONE chunk. Tool-call turns: yield sentinel line `"__TOOL_CALL__"` then continue yielding post-tool answer chunks (reuse existing decision plumbing; simplest correct version acceptable — do not rebuild TaskExecutor integration here).
- Manual impact check REQUIRED: grep callers/wrappers of `chat(` in llm_router/llm_providers; expect ~7 positional-blob wrappers — do NOT refactor them in this task; stream_chat adds alongside.

- [ ] **Step 1: Failing tests** with monkeypatched fake providers:
  - yields ≥3 ordered deltas from healthy provider
  - first provider raises connection error pre-token → second provider's deltas yielded
  - error AFTER first token propagates
  - non-streaming provider yields single chunk equal to full reply
- [ ] **Step 2: Red.** [ ] **Step 3: Implement minimal** (per-provider `_stream_<name>` mirroring existing wrapper style; Ollama: `stream=True`; OpenAI-compatible: `stream=True` parse SSE deltas; Gemini: `generate_content(stream=True)`).
- [ ] **Step 4: Green + `pytest tests/test_llm_router*.py -v` (existing router tests must stay green).**
- [ ] **Step 5: Commit:** `feat(llm): token-level stream_chat with pre-flight fallback`

---

### Task 10: True streaming SSE endpoint + dashboard render

**Files:**
- Modify: `assistant/api_server.py` — `/api/chat/stream` consumes `router.stream_chat`; emit `data: {"delta": "..."}` events then `data: [DONE]`; on upstream error emit `data: {"error": ...}` + DONE (never hang)
- Modify: `dashboard/templates/index.html` — Messages/InputArea consume the SSE stream incrementally (fetch + ReadableStream reader; append deltas to bubble)
- Test: `tests/test_chat_stream_endpoint.py` (new)

- [ ] **Step 1: Failing test:** TestClient with router stubbed `stream_chat` yielding ["Hello", " ", "world"] → response body contains 3 delta events in order + `[DONE]`; error case emits error event + DONE.
- [ ] **Step 2: Implement endpoint; wire frontend reader (progressive textContent append; keep ThinkingIndicator until first delta).**
- [ ] **Step 3: Green + `pytest tests/test_api_contract.py -v`.** [ ] **Step 4: Commit:** `feat(api): true token streaming on /api/chat/stream with incremental dashboard rendering`

---

### Task 11: Echo-safe SPEAKING routing (barge-in preserved)

**Files:**
- Modify: `assistant/audio_manager.py` — add frame routing gate: `set_interrupt_only(True/False)` (during interrupt_only, frames go ONLY to interruption consumer; wake detector/STT receive nothing) and `flush_input()`
- Modify: `main.py` — VoiceAssistant state hooks: on enter SPEAKING → `set_interrupt_only(True)`; on exit → flush + 400ms cooldown before wake detector re-armed; InterruptionVAD keeps receiving frames throughout (do NOT break existing barge-in tests)
- Test: `tests/test_echo_safe_speaking.py` (new)

- [ ] **Step 1: Read main.py:600–760 + audio_manager + state_machine to map frame consumers.** Report flow.
- [ ] **Step 2: Failing tests:** simulated frames during SPEAKING reach interruption callback but wake-word callback receives zero; after exit+cooldown flush, wake receives frames again; cooldown drops frames for N ms.
- [ ] **Step 3: Implement.** [ ] **Step 4: Green + run existing interruption/state tests (`pytest tests/ -k "interrupt or state or audio" -v`).** [ ] **Step 5: Commit:** `fix(voice): isolate TTS echo from wake/STT path while preserving barge-in`

---

### Task 12: Barge-in during PROCESSING

**Files:**
- Modify: `main.py` — extend InterruptionVAD window to PROCESSING; trigger → cancel current turn (reuse TaskExecutor cancel/pause path), optional ack, → LISTENING
- Test: `tests/test_processing_bargein.py` (new)

- [ ] **Step 1: Failing test:** state PROCESSING + speech-above-threshold event → cancel invoked on executor stub, state transitions to LISTENING.
- [ ] **Step 2: Implement minimal (reuse SPEAKING machinery; PROCESSING uses same interrupt_only=False normal routing since mic isn't echoing).** [ ] **Step 3: Green.** [ ] **Step 4: Commit:** `feat(voice): speech barge-in cancels in-flight processing`

---

### Task 13: Python 3.11 standardization + console script

**Files:**
- Modify: `pyproject.toml` — `requires-python = ">=3.11,<3.14"`; `[project.scripts] buddy = "main:main"`
- Rebuild venv: `py -3.11 -m venv venv` (verify `py -3.11` exists; else download via `winget install Python.Python.3.11` — report if blocked), reinstall `-r requirements.txt` + `-e .`, rerun FULL suite on 3.11
- Verify: `.\venv\Scripts\python.exe --version` → 3.11.x; `buddy --help` prints usage (or exits cleanly without hardware)

- [ ] Steps: pin → rebuild → install → `pytest -q` (full, 10 min budget) → `buddy --help` smoke → ruff → fix small compat issues found (record each) → commit `chore(env): standardize on python 3.11, add buddy console entry point`

---

### Task 14: Installer + remove dead Docker files

**Files:**
- Create: `install.ps1` — checks py 3.11, creates venv, `pip install -e ".[dev]"` (or requirements fallback), prefetches models via existing helpers if trivially callable, prints run instructions (`buddy` / `run.ps1`)
- Delete: `Dockerfile`, `docker-compose.yml` (untracked anyway — plain delete); grep `.github/` for docker references and remove if any

- [ ] Steps: write installer → dry-run flag test (`-WhatIf`-style or `--check` mode validating prerequisites without installing) → delete docker files → commit `feat(pkg): windows installer script, remove vestigial docker files`

---

### Task 15: Config consolidation

**Files:**
- Modify: `config.py` + stray readers: `assistant/tts.py` (USE_ELEVENLABS_TTS, PIPER_VOICE_PATH, ElevenLabs voice id → `ELEVENLABS_VOICE_ID` default kept), `assistant/llm_providers.py` (Groq model id → `GROQ_MODEL` default `llama-3.1-8b-instant`), `assistant/wake_word.py.__init__` params, `BUDDY_API_PORT` readers
- Pattern: add typed constants/getters in config.py; modules import from config; env override preserved; defaults byte-identical to today.

- [ ] Step 1: grep `os.getenv|os.environ` outside config.py; table in report: var → module → action (move vs justify-inline).
- [ ] Step 2: Migrate the listed ones only. [ ] Step 3: full targeted suites (`-k "tts or wake or provider"`) + ruff. [ ] Step 4: Commit: `refactor(config): centralize environment access`

---

## Completion

- Final whole-branch review (most capable model) over merge-base..HEAD package + Minor-findings roll-up from ledger.
- Final verification (controller, replaces DeepSeek debate leg): full pytest on 3.11 venv, ruff, manual smoke checklist: dashboard loads with real data + auth, chat streams token-by-token, workflow executes, voice loop echo-safe.
