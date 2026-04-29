# AionUi Pet Companion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Jarvis-side companion API so AionUi's pet can trigger click-to-talk and mirror assistant state.

**Architecture:** Add local Flask dashboard endpoints that reuse the existing injected wake callback and dashboard bridge. The companion wake endpoint rejects overlapping sessions based on current assistant state, while the companion state endpoint returns the current state for reconnect/startup.

**Tech Stack:** Python 3.11, Flask dashboard app, pytest, GitNexus CLI.

---

### Task 1: Companion Wake Endpoint

**Files:**
- Modify: `dashboard/app.py`
- Create: `tests/test_companion_api.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_companion_api.py` with tests for idle wake acceptance and busy-state rejection.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_companion_api.py -q`.

Expected: tests fail because `/api/companion/wake` does not exist yet.

- [ ] **Step 3: Implement minimal wake endpoint**

Add helper state handling and `POST /api/companion/wake` in `dashboard/app.py`. Use `_wake_callback()` only when the current bridge state is not busy.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/test_companion_api.py -q`.

Expected: wake tests pass.

### Task 2: Companion State Endpoint

**Files:**
- Modify: `dashboard/app.py`
- Modify: `tests/test_companion_api.py`

- [ ] **Step 1: Write failing state tests**

Add tests for `GET /api/companion/state` returning `state`, `wake_word_enabled`, and `timestamp`.

- [ ] **Step 2: Verify RED**

Run `python -m pytest tests/test_companion_api.py -q`.

Expected: state endpoint test fails because `/api/companion/state` does not exist yet.

- [ ] **Step 3: Implement minimal state endpoint**

Add `GET /api/companion/state` in `dashboard/app.py`, reading state from `_bridge.current_state()` when available.

- [ ] **Step 4: Verify GREEN**

Run `python -m pytest tests/test_companion_api.py -q`.

Expected: all companion endpoint tests pass.

### Task 3: Verification and Merge

**Files:**
- Modify: `dashboard/app.py`
- Modify: `tests/test_companion_api.py`

- [ ] **Step 1: Run focused tests**

Run `python -m pytest tests/test_companion_api.py tests/test_voice_assistant.py -q`.

- [ ] **Step 2: Run GitNexus change detection**

Run `npx gitnexus detect-changes --scope staged --repo voice-assistant` before committing.

- [ ] **Step 3: Commit branch**

Commit only `dashboard/app.py`, `tests/test_companion_api.py`, and this plan file if it remains useful.

- [ ] **Step 4: Merge branch**

Switch to `master` and merge `codex/aionui-pet-companion` after tests and GitNexus checks pass.
