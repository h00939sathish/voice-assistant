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

## 2026-06-23 — ARVIS OS Dashboard Redesign

Full 3-column AI OS dashboard rebuild. React + Tailwind CSS v4 static site served from `dashboard/`. Three panels: JARVIS Core (left), AI Workspace (center), AI Brain (right). Serves as a companion overlay — loads separately from the Flask backend and communicates via REST + SSE.

Design ethos: deep navy/black, electric blue + subtle gold, glassmorphism, cinematic animations, reactive orb, live system metrics, memory panel, agent feed, automations grid. Every state change animated. Zero empty panels — every section shows live or default placeholder content.

**Key implementation decisions:**
- Ran `npx @tailwindcss/cli init` on `dashboard/` to get Tailwind v4 working standalone
- All CSS via `@import "tailwindcss"` in `style.css` — no JS bundler
- WebSocket connection on `/ws/dashboard` from Flask-SocketIO for real-time data push
- Flask backend already has `dashboard/` blueprint — injects `index.html` which loads `app.js`
- Backend push model: emits JSON events (status, metrics, memory, agent_log, automation, alerts, orb)
- Frontend `app.js` consumes events and mutates store, React re-renders on state changes
- Architecture: no bundler, no JSX transform, no Vite — React loaded from CDN with Babel standalone for JSX in `<script type="text/babel">` tags within `templates/index.html`
- Orb canvas renders via vanilla JS `requestAnimationFrame` (not React) for 60fps animation performance
- Dash avatar: animated SVG path morphing between idle/listening/thinking/speaking/error states

- **Routes to keep** (from existing Flask `dashboard/app.py`):
  - `/` serves `index.html`
  - `/api/status` returns current state
  - `/api/wake` triggers wake
  - `/api/companion/wake` companion wake
  - `/api/companion/state` companion state
  - `/api/chat` text chat
  - `/api/memory` memory panel data
  - `/api/memory/<id>` individual memory
  - `/api/metrics` system metrics
  - `/api/agent/log` agent activity feed
  - `/api/automations` automation list
  - `/api/alerts` system alerts
  - SSE endpoint `/api/events` for live streaming

- **WebSocket events** (server → client):
  - `state` → `{state: "listening"|"thinking"|"speaking"|"error"}`
  - `metrics` → `{cpu, ram, gpu, vram, disk, network}`
  - `providers` → `[{name, status}]`
  - `memory` → `{user, projects, recent, pinned}`
  - `agent_log` → `{timestamp, message}`
  - `automation` → `{id, name, status}`
  - `alert` → `{type, message}`
  - `transcript` → `{text, speaker}`

**Component tree:**
```
App
├── OrbCanvas (vanilla JS, canvas 2d)
├── LeftPanel (JARVIS Core)
│   ├── AvatarArea → orb container
│   ├── VoiceStatus
│   ├── CurrentObjective
│   └── TaskQueue
├── CenterPanel (AI Workspace)
│   ├── ConversationArea
│   │   ├── MessageList
│   │   └── ThinkingIndicator
│   ├── QuickActionsBar
│   └── InputArea
└── RightPanel (AI Brain)
    ├── SystemStatus (CPU, RAM, GPU, disk, providers)
    ├── ActiveModel
    ├── MemoryPanel (user info, projects, recent/pinned memories)
    ├── AgentFeed (live log)
    ├── Automations (running/scheduled/completed/failed)
    └── Alerts (errors, warnings, critical)
```
