# JARVIS Preservation-First Stabilization Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make JARVIS reliable, safe, and daily-useful without removing any major assistant capability.

**Architecture:** Preserve every major capability, but route execution through fewer trusted chokepoints. The core runtime remains voice/orb/dashboard plus `SkillRouter`, `LLMRouter`, `ToolRunner`, `AuthorityGate`, memory, dashboard, and MCP/desktop automation behind explicit gates.

**Tech Stack:** Python 3.11, pytest, pytest-asyncio, SQLite, Flask, PyQt6, Playwright, Ollama/cloud LLM providers, MCP subprocesses, PowerShell run scripts.

---

## Non-Negotiable Constraints

- Do not delete major assistant functions: voice, orb, dashboard, memory, tools, MCP, desktop automation, reminders, browser, vision, LLM providers, and skills stay.
- Duplicated or fragile systems may be disabled by default, feature-flagged, renamed as experimental, or routed through a safer layer.
- Every high-risk action must pass through one safety path.
- Each task must leave the project more runnable than before.

## Target End State

The user can start JARVIS, use typed chat and voice, run low-risk tools, see events in the dashboard, manage memory, and safely attempt desktop/MCP automation. Experimental systems remain available, but they do not corrupt the main runtime.

## Files And Responsibilities

- `assistant/app_init.py`: startup component loading and background preload ownership.
- `main.py`: main runtime wiring, chat/voice path, dashboard bridge callbacks.
- `assistant/tool_runner.py`: single tool execution chokepoint.
- `assistant/authority_gate.py`: risk classification and confirmation decisions.
- `assistant/skill_router.py`: fast skill routing and direct execution policy.
- `assistant/llm_router.py`: provider ordering, tool discovery, task executor integration.
- `assistant/llm_providers.py`: provider health checks and client availability.
- `assistant/tools/code_interpreter.py`: restore missing tool class or disable import cleanly.
- `assistant/tools/__init__.py`: exported tool registry.
- `dashboard/app.py`: local API endpoints and operator controls.
- `.gitignore`: runtime data, logs, caches, vendored dependencies.
- `.github/workflows/ci.yml`: real quality gate.
- `tests/`: regression tests for startup, safety, routing, dashboard, memory, and provider isolation.

---

## Phase 1: Stabilize Core Runtime

### Task 1: Fix Background Preload Ownership

**Files:**
- Modify: `assistant/app_init.py`
- Modify: `main.py`
- Test: `tests/test_startup_preload.py`

- [ ] **Step 1: Write failing test for preload state handoff**

Create `tests/test_startup_preload.py`:

```python
from types import SimpleNamespace

from assistant.app_init import ComponentHandle


def test_component_handle_can_receive_background_components():
    handle = ComponentHandle()
    wake = object()
    task_executor = object()

    handle.set_wake_detector(wake)
    handle.set_task_executor(task_executor)

    assert handle.wake_detector is wake
    assert handle.task_executor is task_executor
```

- [ ] **Step 2: Run test and verify it fails**

Run: `.\venv\Scripts\python.exe -m pytest tests/test_startup_preload.py -q`

Expected: fail because `ComponentHandle` does not exist.

- [ ] **Step 3: Implement component handle**

In `assistant/app_init.py`, add:

```python
from dataclasses import dataclass
from threading import Lock
from typing import Any


@dataclass
class ComponentHandle:
    wake_detector: Any = None
    task_executor: Any = None

    def __post_init__(self) -> None:
        self._lock = Lock()

    def set_wake_detector(self, value: Any) -> None:
        with self._lock:
            self.wake_detector = value

    def set_task_executor(self, value: Any) -> None:
        with self._lock:
            self.task_executor = value
```

Update `preload_components()` to create `handle = ComponentHandle()`, set fields inside the background thread, and return `handle`.

- [ ] **Step 4: Wire main runtime to handle**

In `main.py`, replace:

```python
self.task_executor, self.wake_detector = preload_components(...)
```

with:

```python
self.component_handle = preload_components(...)
self.task_executor = self.component_handle.task_executor
self.wake_detector = self.component_handle.wake_detector
```

In `_process_state()` and `_perform_self_healing()`, read the latest values from `self.component_handle` before using `self.wake_detector` or `self.task_executor`.

- [ ] **Step 5: Verify**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_startup_preload.py tests/test_voice_assistant.py -q
```

Expected: startup preload test passes; voice assistant test no longer fails due to missing memory after Task 2.

### Task 2: Make `VoiceAssistant` Safe To Construct In Tests

**Files:**
- Modify: `main.py`
- Test: `tests/test_voice_assistant.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_voice_assistant.py`:

```python
def test_voice_assistant_creates_default_memory_when_not_injected(mock_audio, mock_stt, mock_tts, mock_llm, mock_skill_router):
    from assistant.events import EventBus
    from main import VoiceAssistant

    assistant = VoiceAssistant(
        audio=mock_audio,
        stt=mock_stt,
        tts=mock_tts,
        llm=mock_llm,
        skill_router=mock_skill_router,
        event_bus=EventBus(persist=False),
    )

    assert assistant.memory is not None
    assert assistant.long_term_memory is not None
```

- [ ] **Step 2: Implement default memory injection**

In `main.py` inside `VoiceAssistant.__init__`, replace:

```python
self.memory = None
self.long_term_memory = None
```

with:

```python
from assistant.conversation_memory import ConversationMemory
from assistant.long_term_memory import LongTermMemory

self.memory = ConversationMemory()
self.long_term_memory = LongTermMemory()
```

Keep the later explicit assignments in `main()` so production can still inject shared instances.

- [ ] **Step 3: Verify**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_voice_assistant.py -q
```

Expected: pass.

---

## Phase 2: Fix Safety Without Removing Capabilities

### Task 3: Restore Confirmation Instead Of Blocking All HIGH Actions

**Files:**
- Modify: `assistant/tool_runner.py`
- Test: `tests/test_foundational_build.py`
- Test: `tests/test_tool_pipeline.py`

- [ ] **Step 1: Confirm current failing tests**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_foundational_build.py::test_tool_runner_denies_confirmation_level_action_before_execution tests/test_foundational_build.py::test_tool_runner_can_disable_terminal_confirmation -q
```

Expected: both fail with `blocked` instead of `requires_confirmation`.

- [ ] **Step 2: Change execution decision flow**

In `assistant/tool_runner.py`, replace the first immediate `if not allowed: return BLOCKED` block with outcome-aware logic:

```python
risk = gate.classify_risk(tool_name, args)
outcome = gate.get_action_outcome(tool_name, args)

if outcome == "blocked":
    result = ToolResult(
        status=ToolStatus.BLOCKED,
        summary=reason,
        tool_name=tool_name,
        args=args,
        duration_ms=self._elapsed_ms(start_ns),
    )
    gate.log_action(tool_name, args, was_approved=False, risk_level=risk)
    self._write_log(result, user_intent)
    return result

if outcome == "confirm":
    dry_run = self._generate_dry_run(tool_name, args)
    approved = await self._request_confirmation(tool_name, args, dry_run)
    if not approved:
        result = ToolResult(
            status=ToolStatus.REQUIRES_CONFIRMATION,
            summary=f"Action '{tool_name}' was denied. Dry-run: {dry_run}",
            tool_name=tool_name,
            args=args,
            duration_ms=self._elapsed_ms(start_ns),
        )
        gate.log_action(tool_name, args, was_approved=False, risk_level=risk)
        self._write_log(result, user_intent)
        return result
    gate.log_action(tool_name, args, was_approved=True, risk_level=risk)
```

Remove the unreachable second `if not allowed:` branch.

- [ ] **Step 3: Verify**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_foundational_build.py tests/test_tool_pipeline.py -q
```

Expected: confirmation tests pass.

### Task 4: Stop Direct High-Risk Skill Bypass

**Files:**
- Modify: `assistant/skill_router.py`
- Modify: `assistant/tool_runner.py`
- Test: `tests/test_skill_safety_routing.py`

- [ ] **Step 1: Add test proving direct routed actions use safety**

Create `tests/test_skill_safety_routing.py`:

```python
import pytest

from assistant.skill_router import SkillRouter
from assistant.tool_runner import ToolResult, ToolStatus


class FakeRunner:
    def __init__(self):
        self.calls = []

    async def execute(self, tool_name, args, user_intent="", context=None):
        self.calls.append((tool_name, args, user_intent))
        return ToolResult(
            status=ToolStatus.OK,
            summary="routed through safety",
            data="routed through safety",
            tool_name=tool_name,
            args=args,
        )


@pytest.mark.asyncio
async def test_direct_skill_routes_through_tool_runner():
    runner = FakeRunner()
    router = SkillRouter(tool_runner=runner)

    response = await router._execute_skill("quick_actions", "open calculator", {})

    assert response == "routed through safety"
    assert runner.calls[0][0] == "quick_actions"
```

- [ ] **Step 2: Add optional `tool_runner` to router**

In `assistant/skill_router.py`, update constructor:

```python
def __init__(self, llm_router=None, tts=None, skills_dir=None, tool_runner=None):
    self.llm = llm_router
    self.tts = tts
    self.tool_runner = tool_runner
```

In `_execute_skill()`, before instantiating the skill:

```python
if self.tool_runner is not None:
    result = await self.tool_runner.execute(
        name,
        {"command": text},
        user_intent=text,
        context=context,
    )
    return result.to_content_str()
```

- [ ] **Step 3: Wire router to LLM tool runner**

In `assistant/app_init.py`, construct `SkillRouter` with:

```python
skill_router = SkillRouter(
    llm_router=llm,
    tts=container.resolve(ITTSProvider),
    tool_runner=llm.get_tool_runner(),
)
```

- [ ] **Step 4: Verify**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_skill_safety_routing.py tests/test_quick_actions_guardrails.py -q
```

Expected: direct quick actions now pass through `ToolRunner`.

---

## Phase 3: Preserve Experiments Behind Stable Boundaries

### Task 5: Fix Or Feature-Flag Broken Agent Core

**Files:**
- Modify: `assistant/tools/code_interpreter.py`
- Modify: `assistant/tools/__init__.py`
- Test: `tests/test_agent_core_import.py`

- [ ] **Step 1: Add import test**

Create `tests/test_agent_core_import.py`:

```python
def test_assistant_core_imports():
    import assistant.core

    assert assistant.core.get_buddy_core is not None
```

- [ ] **Step 2: Restore `CodeInterpreterTool` class**

In `assistant/tools/code_interpreter.py`, move the unreachable code after `return sandbox` into:

```python
class CodeInterpreterTool(BaseTool):
    name = "code_exec"
    description = "Execute Python code in a restricted builtins sandbox and return output"
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
            "timeout": {"type": "integer", "description": "Timeout in seconds", "default": 30},
            "globals": {"type": "object", "description": "Optional globals to pass", "default": {}},
        },
        "required": ["code"],
    }

    async def execute(self, code: str, timeout: int = 30, globals: dict | None = None, **kwargs) -> ToolResult:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()
        local_vars = {}
        if globals:
            local_vars.update(globals)
        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture
            sandbox = create_sandbox()
            exec(code, sandbox.__dict__, local_vars)
            output = stdout_capture.getvalue()
            if stderr_capture.getvalue():
                output += "\n[stderr]: " + stderr_capture.getvalue()
            return ToolResult(success=True, result=output or "Code executed successfully (no output)")
        except Exception as e:
            output = stdout_capture.getvalue()
            output += f"\nError: {e}\n"
            output += traceback.format_exc()
            return ToolResult(success=False, result=output, error=str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr
```

- [ ] **Step 3: Verify**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_agent_core_import.py -q
.\venv\Scripts\python.exe -c "import assistant.core; print('ok')"
```

Expected: both pass.

### Task 6: Mark Experimental Subsystems Without Removing Them

**Files:**
- Modify: `config.py`
- Modify: `assistant/core.py`
- Modify: `assistant/desktop_agent_skill.py`
- Test: `tests/test_experimental_flags.py`

- [ ] **Step 1: Add feature flags**

In `config.py`, add:

```python
ENABLE_EXPERIMENTAL_AGENT_CORE = os.getenv("ENABLE_EXPERIMENTAL_AGENT_CORE", "false").lower() in {"1", "true", "yes"}
ENABLE_DESKTOP_AGENT_SKILL = os.getenv("ENABLE_DESKTOP_AGENT_SKILL", "false").lower() in {"1", "true", "yes"}
ENABLE_MCP_TOOLS = os.getenv("ENABLE_MCP_TOOLS", "true").lower() in {"1", "true", "yes"}
```

- [ ] **Step 2: Use flags in startup/import boundaries**

Keep files present. Do not delete classes. Only prevent experimental paths from loading into normal runtime unless explicitly enabled.

- [ ] **Step 3: Add tests**

Create `tests/test_experimental_flags.py`:

```python
import config


def test_experimental_flags_exist():
    assert hasattr(config, "ENABLE_EXPERIMENTAL_AGENT_CORE")
    assert hasattr(config, "ENABLE_DESKTOP_AGENT_SKILL")
    assert hasattr(config, "ENABLE_MCP_TOOLS")
```

- [ ] **Step 4: Verify**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_experimental_flags.py -q
```

Expected: pass.

---

## Phase 4: Clean Repo Without Removing Functionality

### Task 7: Stop Tracking Runtime State

**Files:**
- Modify: `.gitignore`
- Git index only: untrack runtime files without deleting local copies.

- [ ] **Step 1: Update `.gitignore`**

Add:

```gitignore
# Runtime state
data/*.db
data/*.db-shm
data/*.db-wal
data/*.jsonl
cache/*.db
cache/*.db-shm
cache/*.db-wal
logs/
*.log

# Vendored/generated dependencies
node_modules/
mcp-tools/**/node_modules/

# Local assistant data
.spotify_cache
assistant_backups/
screenshots/
```

- [ ] **Step 2: Untrack runtime state but keep local files**

Run:

```powershell
git rm --cached data/memory.db
```

Expected: file remains locally but is removed from git tracking.

- [ ] **Step 3: Verify**

Run:

```powershell
git status --short
```

Expected: runtime DB/log changes no longer dominate future diffs.

### Task 8: Make CI A Real Gate

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add dev dependencies to install path**

In CI, install:

```yaml
pip install -e ".[dev]"
```

- [ ] **Step 2: Lint assistant and skills**

Change ruff command to:

```yaml
ruff check assistant skills tests --statistics
```

- [ ] **Step 3: Run deterministic tests only**

Use markers or explicit ignores for hardware/live services, but do not silently ignore broken core unit tests. Add a future task to mark hardware tests with `@pytest.mark.hardware`.

- [ ] **Step 4: Verify locally**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest -q
```

Expected after earlier tasks: all non-hardware tests pass.

---

## Phase 5: Daily Utility Upgrade Without Scope Explosion

### Task 9: Define Top 20 Daily Workflows

**Files:**
- Create: `docs/workflows/daily-driver-workflows.md`
- Test: `tests/test_daily_workflow_contracts.py`

- [ ] **Step 1: Document workflows**

Create `docs/workflows/daily-driver-workflows.md` with exactly these categories:

```markdown
# JARVIS Daily Driver Workflows

## Voice And Chat
- Wake assistant and answer a question.
- Type a dashboard chat prompt and receive a response.
- Interrupt speech and ask a follow-up.

## Productivity
- Create reminder.
- List reminders.
- Cancel reminder.
- Ask for today's calendar.
- Ask current time/date.

## Desktop Control
- Open an app.
- Focus a window.
- List files in Downloads.
- Find a file in Documents.
- Read a small text file.

## Research
- Search the web.
- Open a website.
- Extract visible page text.

## Memory
- Remember explicit fact.
- Recall remembered fact.
- Correct remembered fact.
- Forget remembered fact.

## Safety
- Block critical action.
- Request confirmation for high-risk action.
```

- [ ] **Step 2: Add contract test**

Create `tests/test_daily_workflow_contracts.py`:

```python
from pathlib import Path


def test_daily_driver_workflow_doc_exists_and_has_required_sections():
    text = Path("docs/workflows/daily-driver-workflows.md").read_text(encoding="utf-8")
    for heading in [
        "## Voice And Chat",
        "## Productivity",
        "## Desktop Control",
        "## Research",
        "## Memory",
        "## Safety",
    ]:
        assert heading in text
```

- [ ] **Step 3: Verify**

Run:

```powershell
.\venv\Scripts\python.exe -m pytest tests/test_daily_workflow_contracts.py -q
```

Expected: pass.

### Task 10: Add A Single Runtime Smoke Command

**Files:**
- Create: `runtime_smoke_test.py`
- Test: `tests/test_runtime_smoke_import.py`

- [ ] **Step 1: Add import-safe smoke script**

Create `runtime_smoke_test.py`:

```python
import argparse


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-audio", action="store_true")
    parser.add_argument("--no-llm", action="store_true")
    args = parser.parse_args()

    import config
    from assistant.conversation_memory import ConversationMemory
    from assistant.long_term_memory import LongTermMemory
    from assistant.tool_runner import ToolRunner
    from assistant.authority_gate import AuthorityGate

    memory = ConversationMemory()
    long_memory = LongTermMemory()
    gate = AuthorityGate()
    runner = ToolRunner(allow_terminal_confirmation=False)

    assert memory is not None
    assert long_memory is not None
    assert gate is not None
    assert runner is not None
    print("runtime smoke: core imports and local state OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Verify**

Run:

```powershell
.\venv\Scripts\python.exe .\runtime_smoke_test.py --no-audio --no-llm
```

Expected: `runtime smoke: core imports and local state OK`

---

## Execution Order

1. Task 1: startup preload.
2. Task 2: default runtime memory safety.
3. Task 3: confirmation flow.
4. Task 4: route direct skills through safety.
5. Task 5: fix agent core import.
6. Task 7: repo hygiene.
7. Task 8: CI gate.
8. Task 9: daily workflows.
9. Task 10: runtime smoke.
10. Task 6: experimental flags, after the main path is stable.

## Completion Criteria

- `.\venv\Scripts\python.exe -m pytest -q` passes for non-hardware tests.
- `.\venv\Scripts\python.exe .\runtime_smoke_test.py --no-audio --no-llm` passes.
- No major assistant capability is removed.
- High-risk actions request confirmation instead of silently running or being incorrectly blocked.
- Runtime DB/log files are not tracked in git.
- The dashboard still starts and typed chat still routes through the assistant.

