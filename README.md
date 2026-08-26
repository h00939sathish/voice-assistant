# Buddy - Voice Assistant

A **Windows-only** Python voice assistant with wake word detection, multi-provider LLM routing, MCP tools, and a friendly personality.

## AI Assistants: Start Here

**For any AI working on this project:**
```powershell
.\briefing.ps1
```
This provides recent changes, project status, and development context. Full guide: `AI_SESSION_GUIDE.md`

## Features

- 🎤 **Wake Word Detection** - "Hey Jarvis" using openWakeWord
- 🗣️ **VAD-based Listening** - Silero VAD detects when you stop speaking
- 🧠 **Multi-provider LLM Router** - 8 providers (Ollama, LM Studio, Groq, NVIDIA, Gemini, OpenRouter, OpenCode, FreeLLMAPI) with automatic fallback chain
- 🔊 **Streaming TTS Cascade** - ElevenLabs → edge-tts → Piper → pyttsx3 offline fallback
- 🛡️ **Authority Gate** - risk-level approval for tool execution with a SQLite audit trail
- 🔌 **MCP Client + Server** - tools over stdio with dynamic tool discovery
- ✋ **Barge-in** - interrupt speech mid-response by talking over it
- 💬 **Friendly Personality** - Warm, conversational assistant

## Prerequisites

1. **Python 3.10+**
2. **Ollama** (for local LLM):
   ```bash
   # Install from https://ollama.ai
   ollama pull phi4-mini:latest
   ollama pull qwen3.5:4b-q4_K_M
   ollama serve
   ```
3. **Gemini API Key** (for online fallback)

## Installation

```bash
cd c:\Users\h0093\Documents\new
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
```

## Configuration

### Environment Variables

```env
# LLM Settings
GEMINI_API_KEY=your_api_key_here
OLLAMA_MODELS=phi4-mini:latest,qwen3.5:4b-q4_K_M
WHISPER_MODEL=base
LLM_PRIORITY_MODE=local_first  # local_first | cloud_first | online_only

# Wake Word (0.3-0.7, higher = fewer false positives)
WAKE_WORD_STARTUP_ENABLED=false
WAKE_WORD_THRESHOLD=0.5
WAKE_WORD_CONSECUTIVE_HITS=2
WAKE_WORD_COOLDOWN_MS=2000
WAKE_WORD_LOG_SCORES=false
WAKE_WORD_SCORE_LOG_INTERVAL_MS=1000
AUDIO_INPUT_DEVICE=auto  # follows Windows default, or pin by index/name like Airdopes

# VAD (0.3-0.9, higher = less sensitive to background noise)
VAD_THRESHOLD=0.6
SILENCE_DURATION_MS=2000
```

### Configuration Tuning

| Variable | Default | Range | Description |
|----------|---------|-------|-------------|
| `AUDIO_INPUT_DEVICE` | auto | auto/index/name | Follows Windows default while running, or pins a specific mic |
| `WAKE_WORD_STARTUP_ENABLED` | false | true/false | Starts continuous wake-word mode instead of push-to-talk |
| `WAKE_WORD_THRESHOLD` | 0.5 | 0.3-0.7 | Higher = fewer false wake-ups |
| `WAKE_WORD_CONSECUTIVE_HITS` | 2 | 1-3 | Consecutive detections required |
| `WAKE_WORD_COOLDOWN_MS` | 2000 | 500-5000 | Cooldown between detections |
| `WAKE_WORD_LOG_SCORES` | false | true/false | Prints wake model scores for calibration |
| `WAKE_WORD_SCORE_LOG_INTERVAL_MS` | 1000 | 250-5000 | Score logging interval |
| `VAD_THRESHOLD` | 0.6 | 0.3-0.9 | Higher = less sensitive to noise |
| `SILENCE_DURATION_MS` | 2000 | 500-5000 | Silent duration to stop listening |
| `LLM_PRIORITY_MODE` | local_first | local_first/cloud_first/online_only | LLM preference order |

## Usage

```bash
python main.py
```

Say "Hey Jarvis" to activate, speak your question, and wait for the response!

## Architecture

Windows-only desktop app (`python main.py`). Voice pipeline, in-process:

```
mic → openWakeWord ("Hey Jarvis")
    → faster-whisper STT
    → LLMRouter (8 providers with fallback chain)
    → SkillRouter / MCP tools (dynamic tool discovery)
    → AuthorityGate (risk levels + SQLite audit trail)
    → streaming TTS cascade (ElevenLabs → edge-tts → Piper → pyttsx3)
    → speakers
```

State machine:

```
IDLE → WAKE (ding) → LISTENING (VAD) → PROCESSING → SPEAKING (barge-in supported)
  ↑                                                          ↓
  └──────────────────────────────────────────────────────────┘
```

Runtime surfaces (all started by `main.py`):

- **FastAPI control plane** on `http://127.0.0.1:8765` (uvicorn thread; override with `BUDDY_API_PORT`)
- **Flask dashboard** on `http://127.0.0.1:5050` — live SSE streams at `/stream` and `/api/metrics/stream`
- **PyQt6 orb overlay** + pystray system tray
- **SQLite memory** — conversation history plus long-term memory with sqlite-vec vector search

## Personal Stability Scripts

Use these for reliable daily usage:

```powershell
# Quick local checks (no network calls)
.\health_check.ps1

# Deep checks (API keys + MCP connectivity)
.\health_check.ps1 -Deep

# Skip audio hardware checks (for testing without mic)
.\health_check.ps1 -NoAudio

# Skip LLM checks (for offline testing)
.\health_check.ps1 -NoLLM

# Start Buddy with health gate (recommended)
.\run.ps1

# Validate startup path only (no assistant launch)
.\run.ps1 -DryRun

# Start Buddy without preflight checks
.\run.ps1 -SkipHealthCheck

# Skip specific health checks
.\run.ps1 -NoAudio -NoLLM  # Skip audio and LLM checks

# Quiet mode (less output)
.\run.ps1 -Quiet

# Runtime smoke test (mic + wake word + STT + TTS + skill routing)
.\venv\Scripts\python.exe .\runtime_smoke_test.py

# Create timestamped backup into .\assistant_backups (includes data and env files)
.\backup_data.ps1

# Keep only the latest 7 backups
.\backup_data.ps1 -Keep 7

# Project briefing for new AI sessions
.\briefing.ps1
```

## Limitations

- **Windows only** — relies on the `keyboard` hotkey library, `pywinauto`, `pyttsx3`, and Windows default-audio handling; no macOS/Linux support.
- Dashboard Memory panel currently shows only the configured user name; projects/recent/pinned are placeholders (`dashboard/app.py` `/api/memory`).
- Dashboard Active Model panel's context/latency/token stats are not wired yet (shown as "—").
- Piper TTS is skipped unless `PIPER_VOICE_PATH` (and Piper config) are set in `.env`.
