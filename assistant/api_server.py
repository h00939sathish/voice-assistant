"""
Buddy API Server

FastAPI server exposing Buddy's core capabilities.
Supports HTTP REST + WebSocket for real-time voice streaming.

The live VoiceAssistant instance is injected at startup via `set_assistant()`.
All endpoints route through the real assistant pipeline (skills, memory, LLM router).
"""

import asyncio
import base64
import io
import json
import os
import re
import secrets
import struct
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from fastapi import (
    Depends,
    FastAPI,
    File,
    HTTPException,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from config import assert_safe_bind, get_api_token

TOKEN_HEADER = "X-Buddy-Token"
HEALTH_PATH = "/api/health"


def require_token(request: Request = None) -> None:
    """FastAPI dependency: reject requests without a valid X-Buddy-Token.

    Exemptions: CORS preflight (OPTIONS) and GET /api/health only.
    Non-HTTP scopes are authenticated separately at WebSocket accept time
    (see _ws_handshake_ok); this dependency no-ops for those scopes.
    """
    if request is None or request.scope.get("type") != "http":
        return
    if request.method == "OPTIONS":
        return
    if request.url.path == HEALTH_PATH:
        return
    provided = request.headers.get(TOKEN_HEADER, "")
    expected = get_api_token()
    if not provided or not secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid or missing API token")


async def _ws_handshake_ok(websocket: WebSocket) -> bool:
    """WebSocket clients cannot set headers — they pass ?token= on the URL."""
    provided = websocket.query_params.get("token", "")
    expected = get_api_token()
    return bool(provided) and secrets.compare_digest(
        provided.encode("utf-8"), expected.encode("utf-8")
    )


WS_REJECT_CODE = 4401


app = FastAPI(title="Buddy Assistant API", dependencies=[Depends(require_token)])

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://127.0.0.1:5050",
        "http://localhost:5050",
        "http://127.0.0.1:8765",
        "http://localhost:8765",
    ],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["X-Buddy-Token", "Content-Type"],
)

BUDDY_PATH = os.environ.get("BUDDY_PATH", str(Path(__file__).resolve().parent.parent))

AIONUI_LIFECYCLE_LOG_ENABLED = os.environ.get(
    "BUDDY_AIONUI_LIFECYCLE_LOG", ""
).strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
AIONUI_LIFECYCLE_LOG_PATH = Path(BUDDY_PATH) / "logs" / "aionui-lifecycle.log"

# ── Live assistant instance (injected by main.py) ─────────────────────────────
_assistant = None
_state = "IDLE"
active_connections: list[WebSocket] = []
aionui_connections: list[WebSocket] = []

AIONUI_PROTOCOL_VERSION = 3
AIONUI_TICK_INTERVAL_MS = 30000
AIONUI_MAX_PAYLOAD = 25 * 1024 * 1024
AIONUI_MAX_BUFFERED = 10 * 1024 * 1024
AIONUI_FEATURE_METHODS = [
    "connect",
    "sessions.resolve",
    "sessions.reset",
    "sessions.list",
    "chat.send",
    "chat.abort",
    "chat.history",
]
AIONUI_FEATURE_EVENTS = [
    "chat",
    "agent",
    "exec.approval.request",
    "tick",
    "shutdown",
]


def set_assistant(assistant_instance):
    """Called by main.py after VoiceAssistant is created."""
    global _assistant
    _assistant = assistant_instance


def _get_assistant():
    if _assistant is None:
        raise HTTPException(status_code=503, detail="Assistant not initialized yet")
    return _assistant


def set_state(new_state: str):
    """Update Buddy state and broadcast to all WS clients."""
    global _state
    _state = new_state
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None
    if loop and aionui_connections:
        loop.create_task(
            broadcast_aionui_event(
                "agent",
                {
                    "stream": "lifecycle",
                    "data": {"state": new_state.lower(), "timestamp": _now_iso()},
                },
            )
        )
    return {"type": "state_change", "state": new_state}


def _now_iso() -> str:
    return datetime.now().isoformat()


def _log_aionui_lifecycle(state: str, source: str) -> None:
    if not AIONUI_LIFECYCLE_LOG_ENABLED:
        return
    try:
        AIONUI_LIFECYCLE_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(
            {
                "timestamp": _now_iso(),
                "state": state,
                "source": source,
            }
        )
        with AIONUI_LIFECYCLE_LOG_PATH.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except Exception:
        pass


def _split_sentences(text: str) -> list[str]:
    cleaned = text.strip()
    if not cleaned:
        return []
    parts = re.split(r"(?<=[.!?])\s+", cleaned)
    return [p.strip() for p in parts if p.strip()]


def _word_count(text: str) -> int:
    return len(re.findall(r"\b\w+\b", text))


def _should_speak_full(text: str) -> bool:
    sentences = _split_sentences(text)
    if len(sentences) <= 2:
        return True
    return _word_count(text) <= 40


def _summarize_text(text: str) -> str:
    sentences = _split_sentences(text)
    if len(sentences) >= 2:
        summary = " ".join(sentences[:2])
    elif sentences:
        summary = sentences[0]
    else:
        words = text.strip().split()
        summary = " ".join(words[:40])
    if summary:
        return f"{summary} Say 'read full' for more."
    return "Say 'read full' for more."


def _is_read_full_command(text: str) -> bool:
    normalized = text.strip().lower()
    return normalized in {
        "read full",
        "read it",
        "read it all",
        "read full response",
        "read the full response",
        "read full answer",
    }


def _normalize_tool_request(req: "BuddyToolRequest") -> tuple[str, dict[str, Any]]:
    tool_name = (req.tool or req.skill_name or "").strip()
    args = dict(req.args or req.params or {})
    if req.command and "command" not in args:
        args["command"] = req.command
    if tool_name and "command" not in args:
        args["command"] = tool_name
    return tool_name, args


async def _run_chat_pipeline(
    assistant, message: str, speak: bool = False, source: str = "api"
) -> str:
    message = (message or "").strip()
    if not message:
        raise HTTPException(status_code=400, detail="Message is required")
    if hasattr(assistant, "process_text_chat"):
        return await assistant.process_text_chat(message, speak=speak, source=source)
    return await assistant.llm.chat(message)


async def _execute_tool(
    assistant, tool_name: str, args: dict[str, Any]
) -> dict[str, Any]:
    tool_name = (tool_name or "").strip()
    if not tool_name:
        raise HTTPException(status_code=400, detail="Tool name is required")

    skill_router = getattr(assistant, "skill_router", None)
    if not skill_router:
        raise HTTPException(status_code=503, detail="Skill router not available")

    tool_runner = getattr(skill_router, "tool_runner", None) or getattr(
        assistant, "tool_runner", None
    )
    if tool_runner:
        result = await tool_runner.execute(
            tool_name,
            args,
            user_intent=args.get("command", tool_name),
            context={"source": "api_tool"},
        )
        status = getattr(result.status, "value", result.status)
        return {
            "ok": status == "ok",
            "status": status,
            "result": result.data if result.data is not None else result.summary,
            "summary": result.summary,
            "error": result.error,
            "duration_ms": result.duration_ms,
        }

    instance = skill_router._get_skill_instance(tool_name)
    if instance is None:
        raise HTTPException(status_code=404, detail=f"Tool not found: {tool_name}")

    context = {"source": "api_tool"}
    if hasattr(instance, "handle_tool_call"):
        raw = await instance.handle_tool_call(args, context=context)
    else:
        raw = await instance.handle(args.get("command", tool_name), context)
    return {"ok": True, "status": "ok", "result": raw}


def _set_wake_word_enabled(assistant, enabled: bool) -> bool:
    if hasattr(assistant, "set_wake_word_enabled"):
        return bool(assistant.set_wake_word_enabled(enabled))

    assistant._wake_word_enabled = bool(enabled)
    if enabled and hasattr(assistant, "_ensure_mic_active"):
        assistant._ensure_mic_active()
    elif not enabled and hasattr(assistant, "_release_microphone"):
        assistant._release_microphone()
    return bool(getattr(assistant, "_wake_word_enabled", enabled))


async def _speak_text(assistant, text: str) -> None:
    if not text:
        return
    if hasattr(assistant, "tts") and assistant.tts:
        await assistant.tts.speak_streaming(text)
    else:
        from assistant.tts import TextToSpeech

        tts = TextToSpeech()
        await tts.speak_streaming(text)


# ── Models ───────────────────────────────────────────────────────────────────────────
class SpeakRequest(BaseModel):
    text: str
    voice: str | None = None


class ChatRequest(BaseModel):
    message: str
    model: str | None = None
    stream: bool | None = False


class SkillRunRequest(BaseModel):
    skill_name: str
    params: dict | None = {}


class BuddyToolRequest(BaseModel):
    tool: str | None = None
    skill_name: str | None = None
    args: dict | None = None
    params: dict | None = None
    command: str | None = None


class MemoryQueryRequest(BaseModel):
    query: str
    limit: int | None = 5


class DesktopExecuteRequest(BaseModel):
    action: str
    target: str | None = None
    params: dict | None = {}


class WakeWordRequest(BaseModel):
    threshold: float | None = None


# ── Server-side VAD (energy-based, no extra deps) ────────────────────────────
class StreamingVAD:
    """
    Lightweight energy-based Voice Activity Detector.
    Accumulates raw PCM-16 frames, detects speech start/end by RMS energy,
    and yields complete utterance buffers ready for Whisper.

    Protocol the WebSocket client must follow:
      - Send binary frames: raw PCM-16LE, mono, 16 kHz (matching Whisper's native rate)
      - OR send JSON {"type": "voice_config", "sample_rate": N, "channels": 1}
        before streaming to change the expected rate
      - Send JSON {"type": "voice_end"} to force-flush any buffered audio
    """

    # Tuning constants
    FRAME_DURATION_MS = 30  # ms per incoming chunk (client should match)
    SAMPLE_RATE = 16000  # expected PCM rate
    ENERGY_THRESHOLD = 300  # RMS level that counts as speech
    SPEECH_PAD_MS = 300  # ms of silence kept after speech ends
    MIN_SPEECH_MS = 250  # minimum speech duration to bother transcribing
    MAX_SPEECH_SEC = 30  # hard cut-off to prevent unbounded buffering
    SILENCE_TIMEOUT_MS = 800  # ms of silence that ends an utterance

    def __init__(self):
        self.sample_rate = self.SAMPLE_RATE
        self.speaking = False
        self.speech_frames: list[bytes] = []
        self.silence_ms = 0
        self.speech_ms = 0
        self._pad_frames: list[bytes] = []  # ring buffer for pre-speech padding

    def configure(self, sample_rate: int):
        self.sample_rate = sample_rate

    @staticmethod
    def _rms(pcm_bytes: bytes) -> float:
        if len(pcm_bytes) < 2:
            return 0.0
        samples = struct.unpack_from(f"<{len(pcm_bytes) // 2}h", pcm_bytes)
        return (sum(s * s for s in samples) / len(samples)) ** 0.5

    def _frame_ms(self, pcm_bytes: bytes) -> float:
        samples = len(pcm_bytes) // 2
        return (samples / self.sample_rate) * 1000

    def push(self, pcm_bytes: bytes):
        """
        Feed a raw PCM-16LE chunk.
        Returns a complete utterance as bytes when one finishes, else None.
        """
        energy = self._rms(pcm_bytes)
        frame_ms = self._frame_ms(pcm_bytes)
        is_voice = energy > self.ENERGY_THRESHOLD

        if not self.speaking:
            # Keep a rolling pre-speech pad buffer
            self._pad_frames.append(pcm_bytes)
            pad_keep_ms = self.SPEECH_PAD_MS
            while self._pad_frames:
                oldest_ms = self._frame_ms(self._pad_frames[0])
                if (
                    sum(self._frame_ms(f) for f in self._pad_frames) - oldest_ms
                    >= pad_keep_ms
                ):
                    self._pad_frames.pop(0)
                else:
                    break

            if is_voice:
                self.speaking = True
                self.silence_ms = 0
                self.speech_ms = frame_ms
                # Include pre-speech pad so we don't clip word onsets
                self.speech_frames = list(self._pad_frames) + [pcm_bytes]
                self._pad_frames = []
            return None

        # ── Currently speaking ────────────────────────────────────────────
        self.speech_frames.append(pcm_bytes)
        self.speech_ms += frame_ms

        if is_voice:
            self.silence_ms = 0
        else:
            self.silence_ms += frame_ms

        # Hard time-limit cut
        if self.speech_ms >= self.MAX_SPEECH_SEC * 1000:
            return self._flush()

        # Silence-based end-of-utterance
        if self.silence_ms >= self.SILENCE_TIMEOUT_MS:
            return self._flush()

        return None

    def flush(self):
        """Force-flush whatever is buffered (e.g. on voice_end signal)."""
        if self.speech_frames and self.speech_ms >= self.MIN_SPEECH_MS:
            return self._flush()
        self._reset()
        return None

    def _flush(self):
        raw = b"".join(self.speech_frames)
        self._reset()
        if len(raw) < (self.MIN_SPEECH_MS / 1000 * self.sample_rate * 2):
            return None  # too short, discard
        return self._wrap_wav(raw)

    def _reset(self):
        self.speaking = False
        self.speech_frames = []
        self.silence_ms = 0
        self.speech_ms = 0
        self._pad_frames = []

    def _wrap_wav(self, pcm_bytes: bytes) -> bytes:
        """Wrap raw PCM-16 in a WAV container so Whisper can read it."""
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)  # 16-bit
            wf.setframerate(self.sample_rate)
            wf.writeframes(pcm_bytes)
        return buf.getvalue()


@app.get("/")
async def root():
    return {"buddy": "online", "version": "1.0", "state": _state}


@app.get(HEALTH_PATH)
async def health():
    """Unauthenticated liveness probe (the only route exempt from token auth)."""
    return {"status": "ok"}


@app.get("/api/status")
async def status():
    assistant = _assistant
    return {
        "status": "running" if assistant else "starting",
        "state": _state,
        "features": ["wake_word", "stt", "tts", "llm", "memory", "desktop"],
        "assistant": "connected" if assistant else "disconnected",
    }


@app.get("/buddy/status")
async def buddy_status():
    return await status()


@app.get("/api/state")
async def get_state():
    return {"state": _state, "timestamp": datetime.now().isoformat()}


@app.get("/buddy/state")
async def buddy_state():
    return await get_state()


# ── Voice I/O ────────────────────────────────────────────────────────────────
@app.post("/buddy/speak")
@app.post("/api/speak")
async def speak(req: SpeakRequest):
    """Make Buddy speak via TTS."""
    try:
        assistant = _get_assistant()
        set_state("SPEAKING")

        if hasattr(assistant, "tts") and assistant.tts:
            if hasattr(assistant.tts, "speak_streaming"):
                await assistant.tts.speak_streaming(req.text)
            else:
                await asyncio.to_thread(assistant.tts.speak, req.text)
        else:
            from assistant.tts import TextToSpeech

            tts = TextToSpeech()
            await asyncio.to_thread(tts.speak, req.text)

        set_state("IDLE")
        return {"spoken": req.text}
    except Exception as e:
        set_state("ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/chat")
async def chat(req: ChatRequest):
    """Chat with Buddy through the full pipeline (skills, memory, LLM)."""
    try:
        assistant = _get_assistant()
        set_state("THINKING")
        response = await _run_chat_pipeline(
            assistant, req.message, speak=False, source="api_chat"
        )
        set_state("IDLE")
        return {"response": response}
    except HTTPException:
        set_state("IDLE")
        raise
    except Exception as e:
        set_state("ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/buddy/chat")
async def buddy_chat(req: ChatRequest):
    try:
        assistant = _get_assistant()
        set_state("THINKING")
        response = await _run_chat_pipeline(
            assistant, req.message, speak=False, source="buddy_chat"
        )
        set_state("IDLE")
        return {"ok": True, "response": response, "state": _state}
    except HTTPException:
        set_state("IDLE")
        raise
    except Exception as e:
        set_state("ERROR")
        raise HTTPException(status_code=500, detail=str(e))


# ── Skills & Tools ────────────────────────────────────────────────────────────
@app.get("/api/skills")
async def list_skills():
    """List available Buddy skills."""
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "skill_router"):
            skills = assistant.skill_router.get_skill_names()
            return {"skills": skills}
        return {"skills": []}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/buddy/tools")
async def buddy_tools():
    return await list_skills()


@app.post("/api/skills/run")
async def run_skill(req: SkillRunRequest):
    """Execute a Buddy skill via skill router."""
    try:
        assistant = _get_assistant()
        args = dict(req.params or {})
        args.setdefault("command", req.skill_name)
        return await _execute_tool(assistant, req.skill_name, args)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/buddy/tool")
async def buddy_tool(req: BuddyToolRequest):
    try:
        assistant = _get_assistant()
        tool_name, args = _normalize_tool_request(req)
        return await _execute_tool(assistant, tool_name, args)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Memory ───────────────────────────────────────────────────────────────
@app.post("/api/memory/query")
async def memory_query(req: MemoryQueryRequest):
    """Query Buddy's long-term memory."""
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "long_term_memory"):
            results = assistant.long_term_memory.search(req.query, limit=req.limit)
            return {"results": results}
        raise HTTPException(status_code=500, detail="Memory not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Desktop Automation ──────────────────────────────────────────────────
@app.post("/api/desktop/execute")
async def desktop_execute(req: DesktopExecuteRequest):
    """Execute desktop automation action via skill router."""
    try:
        assistant = _get_assistant()
        set_state("THINKING")
        target = f" {req.target}" if req.target else ""
        params = f" with {req.params}" if req.params else ""
        command = f"{req.action}{target}{params}".strip()
        result = await _run_chat_pipeline(
            assistant, command, speak=False, source="api_desktop"
        )
        set_state("IDLE")
        return {"result": result}
    except HTTPException:
        set_state("IDLE")
        raise
    except Exception as e:
        set_state("ERROR")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/desktop/screenshot")
async def desktop_screenshot():
    """Take screenshot via skill router."""
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "skill_router"):
            result = assistant.skill_router.run_skill(
                "desktop", {"action": "screenshot"}
            )
            return {"result": result}
        raise HTTPException(status_code=500, detail="Desktop not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/desktop/windows")
async def desktop_windows():
    """List open windows via skill router."""
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "skill_router"):
            result = assistant.skill_router.run_skill(
                "desktop", {"action": "list_windows"}
            )
            return {"windows": result}
        raise HTTPException(status_code=500, detail="Desktop not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Voice HTTP (WAV upload → STT → pipeline → TTS) ────────────────────────
@app.post("/buddy/voice")
@app.post("/buddy/voice-command")
@app.post("/api/voice")
async def voice_input(file: UploadFile = File(...), speak: bool = True):
    """
    Accept a WAV/PCM audio file, run it through STT → skill pipeline → LLM → (optionally) TTS.

    curl example:
        curl -X POST http://localhost:8765/api/voice \
             -F "file=@recording.wav" -F "speak=true"

    Returns:
        {"transcript": "...", "response": "...", "spoken": true}
    """
    try:
        audio_bytes = await file.read()
        if not audio_bytes:
            raise HTTPException(status_code=400, detail="Empty audio file")

        assistant = _get_assistant()
        set_state("PROCESSING")

        # STT – transcribe the uploaded audio
        text, confidence = await asyncio.to_thread(
            assistant.stt.transcribe, audio_bytes
        )

        if not text or confidence < 0.3:
            set_state("IDLE")
            return {
                "transcript": text,
                "confidence": confidence,
                "dropped": True,
                "reason": "low confidence",
            }

        # Full pipeline: skill router → LLM → memory
        set_state("THINKING")
        final_text, _ = await assistant._handle_user_text(
            text, confidence=confidence, source="api_http_voice"
        )

        # Optional TTS
        if speak and hasattr(assistant, "tts") and assistant.tts:
            set_state("SPEAKING")
            await asyncio.to_thread(assistant.tts.speak, final_text)

        set_state("IDLE")
        return {
            "transcript": text,
            "confidence": confidence,
            "response": final_text,
            "spoken": speak,
        }

    except HTTPException:
        raise
    except Exception as e:
        set_state("ERROR")
        raise HTTPException(status_code=500, detail=str(e))


# ── Wake Word ──────────────────────────────────────────────────────────────
@app.post("/buddy/wake-word/start")
@app.post("/api/wake-word/start")
async def start_wake_word(req: WakeWordRequest = None):
    """Start wake word detection."""
    try:
        assistant = _get_assistant()
        enabled = _set_wake_word_enabled(assistant, True)
        set_state("IDLE")
        return {"status": "wake_word_started", "wake_word_enabled": enabled}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/buddy/wake-word/stop")
@app.post("/api/wake-word/stop")
async def stop_wake_word():
    """Stop wake word detection."""
    try:
        assistant = _get_assistant()
        enabled = _set_wake_word_enabled(assistant, False)
        set_state("IDLE")
        return {"status": "wake_word_stopped", "wake_word_enabled": enabled}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── Companion Bridge (for AionUI pet) ─────────────────────────────────────
@app.get("/api/companion/state")
async def companion_state():
    """Return current state for AionUI desktop pet."""
    assistant = _assistant
    enabled = (
        bool(getattr(assistant, "_wake_word_enabled", False)) if assistant else False
    )
    return {
        "state": _state,
        "wake_word_enabled": enabled,
        "timestamp": datetime.now().isoformat(),
    }


@app.get("/buddy/companion/state")
async def buddy_companion_state():
    return await companion_state()


@app.post("/api/companion/wake")
async def companion_wake():
    """Trigger click-to-talk from external companion (AionUI)."""
    set_state("LISTENING")
    # Broadcast to WebSocket clients
    for conn in active_connections:
        await conn.send_json({"type": "wake_triggered"})
    for conn in aionui_connections:
        await conn.send_json(
            {"type": "event", "event": "companion.wake", "payload": {"state": _state}}
        )
    return {"accepted": True, "state": _state}


@app.post("/buddy/companion/wake")
async def buddy_companion_wake():
    return await companion_wake()


# ── Model Switching ────────────────────────────────────────────────────────
@app.get("/api/models")
async def list_models():
    """List available models (Ollama + cloud)."""
    try:
        _get_assistant()
        models = []

        # Ollama models
        try:
            import ollama

            ollama_models = ollama.list()
            models.extend(
                [{"name": m.model, "provider": "ollama"} for m in ollama_models.models]
            )
        except Exception:
            pass

        # Cloud models based on API keys
        if os.getenv("GEMINI_API_KEY"):
            models.append({"name": "gemini-2.0-flash", "provider": "gemini"})
        if os.getenv("GROQ_API_KEY"):
            models.append({"name": "llama-3.3-70b", "provider": "groq"})

        return {"models": models}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/models/set")
async def set_model(model: str, provider: str = None):
    """Switch the active model."""
    try:
        assistant = _get_assistant()
        if hasattr(assistant, "llm_router"):
            assistant.llm_router.set_preferred_model(model, provider)
            return {"model": model, "provider": provider, "status": "changed"}
        raise HTTPException(status_code=500, detail="LLM router not available")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ── WebSocket ────────────────────────────────────────────────────────────
async def broadcast_ws(event: dict):
    for conn in active_connections:
        try:
            await conn.send_json(event)
        except Exception:
            pass


async def broadcast_aionui_event(
    event: str, payload: dict = None, seq: int = None
) -> None:
    if not aionui_connections:
        return
    frame = {
        "type": "event",
        "event": event,
        "payload": payload or {},
    }
    if seq is not None:
        frame["seq"] = seq
    for conn in list(aionui_connections):
        try:
            await conn.send_json(frame)
        except Exception:
            if conn in aionui_connections:
                aionui_connections.remove(conn)


@app.websocket("/buddy/events")
@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    Unified WebSocket endpoint.

    TEXT frames — JSON control messages:
      {"type": "ping"}
      {"type": "speak",        "text": "..."}
      {"type": "chat_stream",  "message": "..."}
      {"type": "voice_chunk",  "audio": "<base64-WAV>"}   ← legacy: pre-segmented WAV
      {"type": "voice_config", "sample_rate": 16000}      ← configure streaming VAD
      {"type": "voice_end"}                               ← force-flush VAD buffer
      {"type": "wake_word_listen"}
      {"type": "wake_word_stop"}

    BINARY frames — raw PCM-16LE mono @ 16 kHz (or configured rate).
      Server runs VAD on each chunk and fires the full pipeline automatically
      when an utterance boundary is detected. No client-side VAD needed.

    Server → client events:
      {"type": "vad_speech_start"}
      {"type": "vad_speech_end"}
      {"type": "state",      "state": "PROCESSING|THINKING|SPEAKING|IDLE"}
      {"type": "stt_result", "text": "...", "confidence": 0.95}
      {"type": "response",   "text": "..."}
      {"type": "speak_done"}
      {"type": "error",      "error": "..."}
      {"type": "pong"}
    """
    if not await _ws_handshake_ok(websocket):
        await websocket.close(code=WS_REJECT_CODE)
        return
    await websocket.accept()
    active_connections.append(websocket)
    vad = StreamingVAD()
    _pipeline_lock = asyncio.Lock()  # prevent overlapping pipeline calls per connection

    last_full_response = {"text": "", "timestamp": 0.0}

    async def _run_pipeline(wav_bytes: bytes):
        """STT → skill pipeline → LLM → TTS for one utterance."""
        async with _pipeline_lock:
            try:
                assistant = _get_assistant()

                set_state("PROCESSING")
                await websocket.send_json({"type": "state", "state": "PROCESSING"})

                # STT
                text, confidence = await asyncio.to_thread(
                    assistant.stt.transcribe, wav_bytes
                )

                if not text or confidence < 0.4:
                    set_state("IDLE")
                    await websocket.send_json(
                        {
                            "type": "stt_result",
                            "text": text or "",
                            "confidence": confidence,
                            "dropped": True,
                        }
                    )
                    return

                await websocket.send_json(
                    {"type": "stt_result", "text": text, "confidence": confidence}
                )

                # Full pipeline: skill router → LLM → memory
                set_state("THINKING")
                await websocket.send_json({"type": "state", "state": "THINKING"})
                final_text, _ = await assistant._handle_user_text(
                    text, confidence=confidence, source="api_ws_stream"
                )
                await websocket.send_json({"type": "response", "text": final_text})

                last_full_response["text"] = final_text
                last_full_response["timestamp"] = time.time()

                # TTS
                set_state("SPEAKING")
                await websocket.send_json({"type": "state", "state": "SPEAKING"})
                if hasattr(assistant, "tts") and assistant.tts:
                    await asyncio.to_thread(assistant.tts.speak, final_text)
                await websocket.send_json({"type": "speak_done"})

                set_state("IDLE")
                await websocket.send_json({"type": "state", "state": "IDLE"})

            except Exception as e:
                set_state("ERROR")
                await websocket.send_json({"type": "error", "error": str(e)})

    try:
        while True:
            # Receive either binary (raw PCM) or text (JSON control)
            msg = await websocket.receive()

            # ── Binary path: streaming raw PCM ─────────────────────────
            if msg.get("bytes") is not None:
                pcm_chunk = msg["bytes"]
                was_speaking = vad.speaking
                utterance = vad.push(pcm_chunk)

                # Notify client when speech starts
                if not was_speaking and vad.speaking:
                    await websocket.send_json({"type": "vad_speech_start"})

                if utterance:
                    await websocket.send_json({"type": "vad_speech_end"})
                    asyncio.create_task(_run_pipeline(utterance))
                continue

            # ── Text path: JSON control messages ───────────────────────
            raw = msg.get("text", "")
            if not raw:
                continue
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type")

            if msg_type == "ping":
                await websocket.send_json({"type": "pong"})

            elif msg_type == "voice_config":
                sr = int(message.get("sample_rate", 16000))
                vad.configure(sr)
                await websocket.send_json(
                    {"type": "voice_config_ack", "sample_rate": sr}
                )

            elif msg_type == "voice_end":
                # Client signals end of mic stream — flush any buffered audio
                utterance = vad.flush()
                if utterance:
                    await websocket.send_json({"type": "vad_speech_end"})
                    asyncio.create_task(_run_pipeline(utterance))

            elif msg_type == "voice_chunk":
                # Legacy path: pre-segmented base64 WAV from client
                audio_b64 = message.get("audio", "")
                if not audio_b64:
                    await websocket.send_json(
                        {"type": "error", "error": "No audio data"}
                    )
                    continue
                wav_bytes = base64.b64decode(audio_b64)
                asyncio.create_task(_run_pipeline(wav_bytes))

            elif msg_type == "speak":
                text = message.get("text", "")
                try:
                    set_state("SPEAKING")
                    assistant = _get_assistant()
                    if hasattr(assistant, "tts") and assistant.tts:
                        await asyncio.to_thread(assistant.tts.speak, text)
                    else:
                        from assistant.tts import TextToSpeech

                        await asyncio.to_thread(TextToSpeech().speak, text)
                    await websocket.send_json({"type": "speak_done", "text": text})
                    set_state("IDLE")
                except Exception as e:
                    set_state("ERROR")
                    await websocket.send_json({"type": "error", "error": str(e)})

            elif msg_type == "chat_stream":
                user_msg = message.get("message", "")
                try:
                    set_state("THINKING")
                    assistant = _get_assistant()
                    if _is_read_full_command(user_msg) and last_full_response["text"]:
                        await websocket.send_json(
                            {
                                "type": "chat_chunk",
                                "content": last_full_response["text"],
                            }
                        )
                        await websocket.send_json({"type": "chat_done"})
                        set_state("IDLE")
                        continue

                    async for chunk in assistant.llm.stream_chat(user_msg):
                        await websocket.send_json(
                            {"type": "chat_chunk", "content": chunk}
                        )
                    await websocket.send_json({"type": "chat_done"})
                    set_state("IDLE")
                except Exception as e:
                    set_state("ERROR")
                    await websocket.send_json({"type": "error", "error": str(e)})

            elif msg_type in ("wake_word_listen", "wake_word_stop"):
                set_state("LISTENING" if msg_type == "wake_word_listen" else "IDLE")

    except WebSocketDisconnect:
        pass
    finally:
        if websocket in active_connections:
            active_connections.remove(websocket)


@app.websocket("/aionui")
async def aionui_ws_endpoint(websocket: WebSocket):
    if not await _ws_handshake_ok(websocket):
        await websocket.close(code=WS_REJECT_CODE)
        return
    await websocket.accept()
    aionui_connections.append(websocket)
    last_seq = 0
    last_full_response = {"text": "", "timestamp": 0.0}
    tick_task: asyncio.Task | None = None

    def next_seq() -> int:
        nonlocal last_seq
        last_seq += 1
        return last_seq

    async def send_event(
        event: str, payload: dict = None, include_seq: bool = True
    ) -> None:
        frame = {
            "type": "event",
            "event": event,
            "payload": payload or {},
        }
        if include_seq:
            frame["seq"] = next_seq()
        await websocket.send_json(frame)

    async def send_response(
        req_id: str, ok: bool, payload: dict = None, error: dict = None
    ) -> None:
        response = {
            "type": "res",
            "id": req_id,
            "ok": ok,
        }
        if ok:
            response["payload"] = payload or {}
        else:
            response["error"] = error or {
                "code": "REQUEST_FAILED",
                "message": "Request failed",
            }
        await websocket.send_json(response)

    async def handle_connect(params: dict, req_id: str) -> None:
        hello = {
            "type": "hello-ok",
            "protocol": AIONUI_PROTOCOL_VERSION,
            "server": {
                "version": "1.0.0",
                "commit": os.environ.get("BUDDY_BUILD", "local"),
                "host": "localhost",
                "connId": str(uuid4()),
            },
            "features": {
                "methods": AIONUI_FEATURE_METHODS,
                "events": AIONUI_FEATURE_EVENTS,
            },
            "snapshot": {
                "presence": [
                    {
                        "connId": "buddy",
                        "clientId": "buddy",
                        "displayName": "Buddy",
                        "role": "assistant",
                        "scopes": ["operator.admin"],
                        "mode": "backend",
                        "caps": ["tool-events"],
                    }
                ],
                "stateVersion": {"snapshot": 1, "presence": 1},
            },
            "policy": {
                "maxPayload": AIONUI_MAX_PAYLOAD,
                "maxBufferedBytes": AIONUI_MAX_BUFFERED,
                "tickIntervalMs": AIONUI_TICK_INTERVAL_MS,
            },
        }
        await send_response(req_id, True, hello)

    async def emit_state_event(state: str) -> None:
        await send_event(
            "agent",
            {
                "stream": "lifecycle",
                "data": {"state": state, "timestamp": _now_iso()},
            },
        )

    async def tick_loop() -> None:
        while True:
            await asyncio.sleep(AIONUI_TICK_INTERVAL_MS / 1000)
            await send_event("tick", {"ts": int(time.time() * 1000)})

    async def handle_chat_send(params: dict, req_id: str) -> None:
        message = str(params.get("message") or "").strip()
        session_key = str(params.get("sessionKey") or "")
        run_id = str(uuid4())
        await send_response(req_id, True, {"status": "accepted", "runId": run_id})
        if not message:
            await send_event(
                "chat",
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "state": "error",
                    "errorMessage": "Empty message",
                },
            )
            return

        if _is_read_full_command(message) and last_full_response["text"]:
            full_text = last_full_response["text"]
            await send_event(
                "chat",
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": 1,
                    "state": "delta",
                    "message": {"content": full_text},
                },
            )
            await send_event(
                "chat",
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": 2,
                    "state": "final",
                    "message": {"content": full_text},
                },
            )
            await emit_state_event("speaking")
            await _speak_text(_get_assistant(), full_text)
            await emit_state_event("idle")
            return

        try:
            assistant = _get_assistant()
            await emit_state_event("thinking")
            response_text = await assistant.process_text_chat(
                message, speak=False, source="aionui"
            )
        except Exception as e:
            await emit_state_event("error")
            await send_event(
                "chat",
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "state": "error",
                    "errorMessage": str(e),
                },
            )
            return

        last_full_response["text"] = response_text
        last_full_response["timestamp"] = time.time()

        if _should_speak_full(response_text):
            await send_event(
                "chat",
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": 1,
                    "state": "delta",
                    "message": {"content": response_text},
                },
            )
            await send_event(
                "chat",
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": 2,
                    "state": "final",
                    "message": {"content": response_text},
                },
            )
            await emit_state_event("speaking")
            await _speak_text(assistant, response_text)
        else:
            summary = _summarize_text(response_text)
            await send_event(
                "chat",
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": 1,
                    "state": "delta",
                    "message": {"content": summary},
                },
            )
            await send_event(
                "chat",
                {
                    "runId": run_id,
                    "sessionKey": session_key,
                    "seq": 2,
                    "state": "final",
                    "message": {"content": summary},
                },
            )
            await emit_state_event("speaking")
            await _speak_text(assistant, summary)

        await emit_state_event("idle")

    async def handle_chat_abort(params: dict, req_id: str) -> None:
        await send_response(req_id, True, {"status": "ok"})

    async def handle_sessions_resolve(params: dict, req_id: str) -> None:
        key = str(params.get("key") or params.get("sessionId") or str(uuid4()))
        await send_response(req_id, True, {"key": key, "sessionId": key})

    async def handle_sessions_reset(params: dict, req_id: str) -> None:
        key = str(params.get("key") or str(uuid4()))
        await send_response(req_id, True, {"key": key, "sessionId": key})

    async def handle_sessions_list(req_id: str) -> None:
        await send_response(req_id, True, {"sessions": []})

    async def handle_chat_history(params: dict, req_id: str) -> None:
        await send_response(req_id, True, {"messages": []})

    async def handle_request(req: dict) -> None:
        req_id = req.get("id")
        method = str(req.get("method") or "")
        params = req.get("params") or {}
        if not req_id:
            return
        if method == "connect":
            await handle_connect(params, req_id)
            return
        if method == "chat.send":
            await handle_chat_send(params, req_id)
            return
        if method == "chat.abort":
            await handle_chat_abort(params, req_id)
            return
        if method == "sessions.resolve":
            await handle_sessions_resolve(params, req_id)
            return
        if method == "sessions.reset":
            await handle_sessions_reset(params, req_id)
            return
        if method == "sessions.list":
            await handle_sessions_list(req_id)
            return
        if method == "chat.history":
            await handle_chat_history(params, req_id)
            return

        await send_response(
            req_id,
            False,
            error={
                "code": "METHOD_NOT_FOUND",
                "message": f"Method not found: {method}",
            },
        )

    try:
        tick_task = asyncio.create_task(tick_loop())
        await send_event(
            "connect.challenge", {"nonce": str(uuid4()), "ts": int(time.time() * 1000)}
        )
        while True:
            msg = await websocket.receive()
            if msg.get("type") == "disconnect":
                break
            raw = msg.get("text") or ""
            if not raw:
                continue
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                continue

            if parsed.get("type") == "req":
                await handle_request(parsed)
    except WebSocketDisconnect:
        pass
    finally:
        if tick_task:
            tick_task.cancel()
        if websocket in aionui_connections:
            aionui_connections.remove(websocket)


# ── Streaming Chat ────────────────────────────────────────────────────────
@app.post("/buddy/chat/stream")
@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """Streaming chat response via SSE."""

    async def event_stream():
        try:
            assistant = _get_assistant()
            set_state("THINKING")

            if hasattr(assistant.llm, "stream_chat"):
                async for chunk in assistant.llm.stream_chat(req.message):
                    yield f"data: {json.dumps({'chunk': chunk})}\n\n"
            else:
                response = await _run_chat_pipeline(
                    assistant, req.message, speak=False, source="api_chat_stream"
                )
                yield f"data: {json.dumps({'chunk': response})}\n\n"

            set_state("IDLE")
            yield f"data: {json.dumps({'done': True})}\n\n"
        except Exception as e:
            yield f"data: {json.dumps({'error': str(e)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


# ── Run Server ────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("BUDDY_API_PORT", "8765"))
    host = "127.0.0.1"
    assert_safe_bind(host)
    uvicorn.run(app, host=host, port=port, log_config=None, access_log=False)
