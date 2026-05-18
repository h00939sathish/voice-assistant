# Buddy Next Build — Foundation & Trust

## Goal
Central execution wrapper, centralized safety policy, memory categorization + correction, minimal task state machine, event/log pipeline, thin dashboard.

## Tasks
- [ ] Task 1: Create `assistant/tool_runner.py` — unified execution with normalized results, JSONL logging, idempotency-aware retries, dry-run generation → Verify: `test_tool_pipeline.py` passes
- [ ] Task 2: Update `assistant/authority_gate.py` — single policy registry from `data/safety_policy.json`, confirmation transport (GUI/terminal/timeout), safe/confirm/blocked mapping → Verify: `test_confirmation_flow.py` passes
- [ ] Task 3: Slim `assistant/llm_router.py` — replace inline gate+execution blocks with `tool_runner.execute()` calls → Verify: `test_tool_pipeline.py` integration passes
- [ ] Task 4: Expand `assistant/long_term_memory.py` — schema versioning, v1→v2 migration, new categories with write policies, correction flows (remember/forget/correct/always_do) → Verify: `test_memory_migration.py` passes
- [ ] Task 5: Create `assistant/task_executor.py` — state model, step loop, pause/resume with JSON serialization, basic verification hooks → Verify: `test_task_pause_resume.py` passes
- [ ] Task 6: Create `assistant/event_bus.py` — pub/sub event model + JSONL persistence → Verify: events emitted by tool_runner appear in JSONL
- [ ] Task 7: Create `gui/operator_dashboard.py` — pure event_bus consumer showing actions, health, failures → Verify: dashboard renders mock events
- [ ] Task 8: Integration wiring + manual smoke test → Verify: end-to-end flow from voice command to logged execution

## Done When
- [ ] All tool execution flows through `tool_runner.py`
- [ ] Destructive actions show dry-run and require confirmation
- [ ] Memory categories are migrated and correction flows work
- [ ] Tasks can be paused and resumed across restarts
- [ ] Dashboard displays live system state from event stream
