<!-- gitnexus:start -->
# GitNexus — Code Intelligence

This project is indexed by GitNexus as **voice-assistant** (78311 symbols, 125252 relationships, 300 execution flows). Use the GitNexus MCP tools to understand code, assess impact, and navigate safely.

> If any GitNexus tool warns the index is stale, run `npx gitnexus analyze` in terminal first.

## Always Do

- **MUST run impact analysis before editing any symbol.** Before modifying a function, class, or method, run `gitnexus_impact({target: "symbolName", direction: "upstream"})` and report the blast radius (direct callers, affected processes, risk level) to the user.
- **MUST run `gitnexus_detect_changes()` before committing** to verify your changes only affect expected symbols and execution flows.
- **MUST warn the user** if impact analysis returns HIGH or CRITICAL risk before proceeding with edits.
- When exploring unfamiliar code, use `gitnexus_query({query: "concept"})` to find execution flows instead of grepping. It returns process-grouped results ranked by relevance.
- When you need full context on a specific symbol — callers, callees, which execution flows it participates in — use `gitnexus_context({name: "symbolName"})`.

## Never Do

- NEVER edit a function, class, or method without first running `gitnexus_impact` on it.
- NEVER ignore HIGH or CRITICAL risk warnings from impact analysis.
- NEVER rename symbols with find-and-replace — use `gitnexus_rename` which understands the call graph.
- NEVER commit changes without running `gitnexus_detect_changes()` to check affected scope.

## Resources

| Resource | Use for |
|----------|---------|
| `gitnexus://repo/voice-assistant/context` | Codebase overview, check index freshness |
| `gitnexus://repo/voice-assistant/clusters` | All functional areas |
| `gitnexus://repo/voice-assistant/processes` | All execution flows |
| `gitnexus://repo/voice-assistant/process/{name}` | Step-by-step execution trace |

## CLI

| Task | Read this skill file |
|------|---------------------|
| Understand architecture / "How does X work?" | `.claude/skills/gitnexus/gitnexus-exploring/SKILL.md` |
| Blast radius / "What breaks if I change X?" | `.claude/skills/gitnexus/gitnexus-impact-analysis/SKILL.md` |
| Trace bugs / "Why is X failing?" | `.claude/skills/gitnexus/gitnexus-debugging/SKILL.md` |
| Rename / extract / split / refactor | `.claude/skills/gitnexus/gitnexus-refactoring/SKILL.md` |
| Tools, resources, schema reference | `.claude/skills/gitnexus/gitnexus-guide/SKILL.md` |
| Index, status, clean, wiki CLI commands | `.claude/skills/gitnexus/gitnexus-cli/SKILL.md` |

<!-- gitnexus:end -->

# Session Anchors

## 2026-08-26 — Dashboard reality pass (post-remediation Tasks 1–4)

Facts below verified against code after Tasks 1–4 of the 2026-08 honesty/security
remediation (`docs/superpowers/plans/2026-08-26-buddy-remediation.md`). The workflow
engine executes for real; fictional dashboard panels were removed; remaining panels
serve live data.

**Dashboard stack (actual):**
- Plain Flask app in `dashboard/app.py`, run_server defaults to `127.0.0.1:5050` (CLI overrides: `--dashboard-host` / `--dashboard-port` in `assistant/cli_parser.py`). No Flask-SocketIO anywhere in the repo.
- Frontend is a single `dashboard/templates/index.html`: React 18 UMD from unpkg, hand-rolled `h()` createElement helper, inline store — no Babel, no JSX transform, no bundler. (`dashboard/static/app.js` was deleted.)
- Styling: hand-written CSS in `dashboard/static/style.css` (~940 lines). No Tailwind.
- Live data: two SSE streams — `/stream` (bridge events) and `/api/metrics/stream` (system telemetry every 3 s).
- Panels render live data only; sections without a live source are removed, not faked.

**Routes** (exact, from `dashboard/app.py`):
- Page: `GET /`
- SSE: `GET /stream`, `GET /api/metrics/stream`
- REST: `GET /api/status`, `GET /api/objective`, `GET /api/tasks`, `GET /api/model-routing`, `GET /api/memory`, `GET /api/agent/log`, `GET /api/system/info`, `GET /api/operator`, `GET /api/execution_log`, `GET /jarvis/state` (Live2D/pet abstraction)
- Actions: `POST /api/wake`, `POST /api/companion/wake`, `POST /api/clear_memory`, `POST /api/toggle_mic`, `POST /api/confirm`, `POST /api/chat`, `POST /api/reminder/<rid>/cancel`; `GET /api/companion/state`, `GET /api/reminders`

**Bridge event types** (server → client, SSE `{type, data}` envelopes from `assistant/dashboard_bridge.py`):
- `state`, `message`, `status`, `tool`, `task`, `subsystem`, `confirmation`
- plus `metrics` on the separate `/api/metrics/stream` endpoint

**Component tree** (`dashboard/templates/index.html`):
```
App
├── LeftPanel
│   ├── MascotSection (DashMascot SVG + orb canvas + state badge + LiveObjective)
│   ├── VoiceStatus
│   └── EnhancedTaskQueue (live TaskExecutor data)
├── CenterPanel
│   ├── MissionControl (empty state) | Messages
│   ├── ThinkingIndicator
│   ├── QuickActions
│   └── InputArea
├── RightPanel
│   ├── SystemStatus (live metrics + provider health dots)
│   ├── ActiveModel (online provider from health checks)
│   ├── AgentFeed (live tool-event log)
│   ├── EnhancedModelRouting (live provider health rows)
│   └── MemoryPanel
└── CommandPalette (Ctrl/Cmd+K)
```

**Other runtime surfaces:** FastAPI control plane on `127.0.0.1:8765` (uvicorn thread, `BUDDY_API_PORT` env override, `assistant/api_server.py`); PyQt6 orb overlay + pystray system tray (`main.py`).
