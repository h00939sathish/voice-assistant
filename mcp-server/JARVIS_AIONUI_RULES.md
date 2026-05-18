# Jarvis Voice Assistant

## Who I Am
I am Jarvis — a voice-enabled AI assistant running locally on this computer.
I have a full pipeline: wake word detection, speech-to-text (Whisper), LLM reasoning (Ollama + cloud fallback), text-to-speech (Edge TTS / Piper), and a skill router with tools for weather, calendar, reminders, browser automation, system control, Spotify, and more.

## How to Use My Tools
Always prefer calling my MCP tools over doing things yourself when they overlap:

- **buddy_chat** — Send any natural language request through my full skill + LLM pipeline. This is the primary tool. Routes through weather, calendar, reminders, browser, system, memory, and more automatically.
- **buddy_voice** — Send base64-encoded WAV audio for full voice processing: STT → skill pipeline → LLM → TTS. Use when you have audio bytes. The complete voice round-trip.
- **buddy_speak** — Make me say something out loud (TTS). Use this to give voice responses.
- **buddy_wake** — Trigger my listening mode (like saying "Hey Jarvis").
- **buddy_memory_query** — Search my long-term memory for past conversations and learned facts.
- **buddy_clear_memory** — Clear my conversation history.
- **buddy_skills** — List all my available skills.
- **buddy_run_skill** — Run a specific skill directly (time, weather, calendar, reminder, browser, system, memory).
- **buddy_desktop_execute** — Control the desktop: open apps, click things, automate windows.
- **buddy_desktop_screenshot** — Take a screenshot.
- **buddy_desktop_windows** — List all open windows.
- **buddy_reminders** — Get pending reminders.
- **buddy_models** — List all available LLM models (local Ollama + cloud).
- **buddy_set_model** — Switch to a different model (e.g. phi4-mini, gemini-2.0-flash, llama3.2).
- **buddy_operator_status** — Get full health dashboard: LLM status, subsystem health, recent tool calls.

## Voice Input — How It Works Now
Buddy now accepts voice input over both HTTP and WebSocket:

### HTTP (single audio file):
```
POST http://localhost:8765/api/voice
Content-Type: multipart/form-data
  file: <WAV audio bytes>
  speak: true/false

Response: {"transcript": "...", "response": "...", "spoken": true}
```

### WebSocket (streaming / real-time):
```
ws://localhost:8765/ws
Send: {"type": "voice_chunk", "audio": "<base64-WAV>", "format": "wav"}
Receive: state updates + stt_result + response + speak_done
```

### Via MCP tool:
```
buddy_voice(audio_base64="<base64-WAV>", speak=True)
```

## Core Principles
- Always check buddy_status first if unsure whether I'm running
- For any task involving time, weather, reminders, or system control — use buddy_chat or buddy_run_skill
- For voice round-trips — use buddy_voice (STT + pipeline + TTS in one call)
- If the user asks you to "tell Jarvis" something — use buddy_speak + buddy_chat
- If the user wants a voice response — always call buddy_speak with the reply text
- Combine AionUI's own capabilities (file ops, document creation, web search) with my voice/skill pipeline for best results

## My State Machine
IDLE → LISTENING → PROCESSING → THINKING → SPEAKING → IDLE
Check buddy_state to see where I am before sending commands.

## Endpoints Summary
| Endpoint | Method | Purpose |
|---|---|---|
| /api/status | GET | Health + state |
| /api/state | GET | Current state |
| /api/chat | POST | Text chat (full pipeline) |
| /api/voice | POST | Voice input (WAV → STT → pipeline → TTS) |
| /api/speak | POST | TTS only |
| /api/skills | GET | List skills |
| /api/skills/run | POST | Run a skill |
| /api/memory/query | POST | Search memory |
| /api/models | GET | List models |
| /api/models/set | POST | Switch model |
| /api/desktop/execute | POST | Desktop automation |
| /api/desktop/screenshot | GET | Screenshot |
| /api/desktop/windows | GET | List windows |
| /api/companion/state | GET | AionUI pet state |
| /api/companion/wake | POST | Trigger wake from AionUI |
| /ws | WebSocket | Real-time voice/chat stream |
