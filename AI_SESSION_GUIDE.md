# AI Session Onboarding Guide

This file provides instructions for any AI assistant working on the JARVIS project.

---

## START HERE: Run This First

```powershell
.\briefing.ps1
```

This script provides:
- Recent changes since your last session
- Uncommitted modifications
- GitNexus index status
- Quick reference commands

---

## Project Overview

**Project:** JARVIS / Buddy Voice Assistant
**Type:** Python voice assistant with wake-word detection, multi-LLM support, skill-based tool execution
**Repo:** voice-assistant

### Key Directories
- `assistant/` — Core AI system (LLM routing, skills, memory, tools)
- `skills/` — 24 skill modules (weather, calendar, browser, etc.)
- `mcp-tools/` — MCP server implementations
- `gui/` — Dashboard and overlay UI
- `tests/` — Test suite (20+ test files)
- `data/` — SQLite databases, event logs

### Core Components
| Component | File | Purpose |
|-----------|------|---------|
| LLM Router | `assistant/llm_router.py` | Multi-provider routing (Ollama, Gemini, Groq, etc.) |
| Skill Router | `assistant/skill_router.py` | Skill-based command routing |
| Long-Term Memory | `assistant/long_term_memory.py` | Persistent semantic memory |
| Voice Pipeline | `main.py` | Wake word → STT → LLM → TTS |
| MCP Integration | Various in `mcp-tools/` | DesktopCommander, planner, router, memory |

---

## GitNexus Code Intelligence

This project uses GitNexus for codebase navigation.

### Quick Commands
```bash
# New session - always run briefing first
.\briefing.ps1

# Check index status
gitnexus status --repo voice-assistant

# Find code by concept
gitnexus query "concept" --repo voice-assistant

# Get symbol details (callers, callees, imports)
gitnexus context "SymbolName" --repo voice-assistant

# Impact analysis before editing
gitnexus impact "SymbolName" --repo voice-assistant --direction upstream
```

### Impact Analysis Rules
- **LOW risk:** Only test/verify files affected
- **MEDIUM risk:** Review 3-4 files after changes
- **HIGH risk:** Full test suite required
- **CRITICAL risk:** Extensive testing + manual verification

---

## Development Workflow

### Before Making Changes
1. Run `.\briefing.ps1` to see recent changes
2. Run `gitnexus detect_changes --scope staged --repo voice-assistant` to see uncommitted changes
3. Run `gitnexus impact "SymbolName" --repo voice-assistant --direction upstream` to check blast radius

### After Making Changes
1. Test changes: `python runtime_smoke_test.py`
2. Run tests: `python -m pytest tests/`
3. Re-index: `gitnexus analyze --force`
4. Commit: `git commit -m "description"`

### Common Tasks
| Task | Command |
|------|---------|
| Start assistant | `python main.py` |
| Health check | `.\health_check.ps1 -Deep` |
| Backup data | `.\backup_data.ps1` |
| Run tests | `python -m pytest tests/ -v` |
| Lint | `python -m ruff check .` |

---

## Configuration Tuning

### Wake Word (config.py + .env)
| Variable | Default | Range | Purpose |
|----------|--------|-------|---------|
| `WAKE_WORD_THRESHOLD` | 0.5 | 0.3-0.7 | Higher = fewer false wake-ups |
| `WAKE_WORD_CONSECUTIVE_HITS` | 2 | 1-3 | Consecutive detections required |
| `WAKE_WORD_COOLDOWN_MS` | 2000 | 500-5000 | Cooldown between triggers |

### VAD (config.py + .env)
| Variable | Default | Range | Purpose |
|----------|--------|-------|---------|
| `VAD_THRESHOLD` | 0.6 | 0.3-0.9 | Higher = less noise sensitive |
| `SILENCE_DURATION_MS` | 2000 | 500-5000 | Stop listening after silence |

### LLM Mode (config.py + .env)
| Variable | Options | Purpose |
|----------|--------|---------|
| `LLM_PRIORITY_MODE` | local_first/cloud_first/online_only | Which LLM to try first |

### Code
- Async/await for I/O operations
- Type hints where used
- Docstrings for public APIs
- Error handling with try/except + logging

### Skills
- Located in `skills/` directory
- Inherit from `BaseSkill`
- Use `@skill` decorator for registration
- Lazy loading with LRU eviction

### Testing
- Unit tests in `tests/test_*.py`
- Use `pytest` framework
- Mock external dependencies

---

## Troubleshooting

### GitNexus Issues
```bash
# Re-index if stale
gitnexus analyze --force

# Check status
gitnexus status
```

### Assistant Issues
```bash
# Deep health check
.\health_check.ps1 -Deep

# Runtime smoke test
.\runtime_smoke_test.py
```

### Git Issues
```bash
# Check uncommitted changes
git status

# View diff
git diff --stat
```

---

## Getting Help

- Run `.\briefing.ps1 -Full` for full reference
- Check `CLAUDE.md` for Claude Code specifics
- Check `AGENTS.md` for agent rules
- Review `README.md` for project overview

---

*Last updated: 2026-04-25*