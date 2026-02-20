# GEMINI.md - Buddy Voice Assistant Context

## Project Overview
**Buddy** is a highly modular, Python-based voice assistant designed for desktop use. It integrates advanced speech processing, multi-provider LLM routing, and a robust skill system to provide a seamless, interactive experience. The project also incorporates the **Antigravity Kit**, a sophisticated agentic framework for expanding AI capabilities.

### Key Technologies
- **Core:** Python 3.10+, `asyncio` for concurrency.
- **Audio & Speech:** `PyAudio`, `openWakeWord` (wake word), `faster-whisper` (STT), `silero-vad` (Voice Activity Detection), `edge-tts` & `pyttsx3` (TTS).
- **Intelligence:** `Ollama` (local LLM), `google-generativeai` (Gemini), `Groq`, `NVIDIA`, `OpenRouter`.
- **Memory:** SQLite-based conversation memory and `sqlite-vec` for long-term vector memory.
- **Interface:** `PyQt6` (Orb overlay), `pystray` (System Tray).
- **Extensibility:** Custom Skill system and **Model Context Protocol (MCP)** support.

---

## Directory Structure
- `main.py`: Main entry point for the desktop application.
- `config.py`: Centralized configuration and environment variable loading.
- `assistant/`: Core logic modules (audio, STT, TTS, LLM routing, memory, etc.).
- `skills/`: Individual skill implementations (e.g., weather, Spotify, calendar).
- `.agent/`: **Antigravity Kit** - A comprehensive toolkit with 19 specialist agents, 36 skills, and 11 workflows.
- `gui/`: UI components for the tray icon and the Siri-like Orb overlay.
- `mcp-tools/`: External MCP server implementations (e.g., DesktopCommander).
- `data/`: Persistent storage, including the long-term memory database.
- `logs/`: Application execution logs.

---

## Building and Running

### Prerequisites
- **Python 3.10+**
- **Ollama** (optional, for local LLM support): `ollama serve` and `ollama pull llama3.2`.
- **API Keys:** Defined in a `.env` file (see `.env.example`).

### Setup
1. Create and activate a virtual environment:
   ```bash
   python -m venv venv
   .\venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Execution
- Run the main application:
  ```bash
  python main.py
  ```
- Use `python start_buddy.py` or `start_buddy.vbs` for background/persistent startup.

---

## Development Conventions

### Architecture
- **State Machine:** The assistant transitions between `IDLE`, `LISTENING`, `PROCESSING`, and `SPEAKING` states.
- **LLM Routing:** Uses a priority-based fallback system (Local Ollama -> Cloud Providers).
- **Skill Routing:** Intent-based routing to specific skill classes before falling back to general LLM chat.
- **Async First:** Most network and heavy I/O operations are handled asynchronously.

### Coding Style
- **Type Hinting:** Extensive use of Python type hints for clarity and stability.
- **Logging:** Centralized logging via `assistant/logger.py`.
- **Modularity:** New functionality should be implemented as a "Skill" in the `skills/` directory or an "Agent" in the `.agent/` framework.

### Memory & Context
- **Conversation Memory:** Short-term history maintained during a session.
- **Long-term Memory:** Fact extraction and vector search used to provide persistent user context across sessions.

---

## Antigravity Kit Integration
The `.agent` directory contains a meta-framework that allows Buddy to act as an orchestrator for specialized agents. 
- Use `/plan` to breakdown complex tasks.
- Use `/create` for implementing new features.
- Consult `.agent/ARCHITECTURE.md` for a full mapping of agents and skills.

---

## Key Files for Reference
- `config.py`: All thresholds, models, and API settings.
- `assistant/llm_router.py`: Logic for provider selection and tool calling.
- `assistant/skill_router.py`: How user intent is mapped to functionality.
- `assistant/stt.py` & `assistant/tts.py`: Speech processing pipelines.
- `data/memory.db`: SQLite database for long-term intelligence.
