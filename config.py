"""
Configuration module for Buddy Voice Assistant
"""

import logging
import os
import secrets
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Load environment variables (force override system defaults)
load_dotenv(override=True)

# Ensure Google SDK uses the correct key if both are present
if os.getenv("GEMINI_API_KEY"):
    os.environ["GOOGLE_API_KEY"] = os.getenv("GEMINI_API_KEY")

# Paths
BASE_DIR = Path(__file__).parent
ASSETS_DIR = BASE_DIR / "assets"
SOUNDS_DIR = ASSETS_DIR / "sounds"

# Audio settings
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 1280  # openWakeWord strictly expects 1280 chunks or multiples
AUDIO_INPUT_DEVICE = os.getenv(
    "AUDIO_INPUT_DEVICE", "auto"
).strip()  # auto, device index, or name substring

# Wake word settings
WAKE_WORD_MODEL = "hey_jarvis"  # Built-in openWakeWord model
WAKE_WORD_THRESHOLD = float(
    os.getenv("WAKE_WORD_THRESHOLD", "0.5")
)  # Higher threshold = fewer false positives (0.3-0.7 range)
WAKE_WORD_CONSECUTIVE_HITS = int(
    os.getenv("WAKE_WORD_CONSECUTIVE_HITS", "2")
)  # Require N consecutive detections
WAKE_WORD_COOLDOWN_MS = int(
    os.getenv("WAKE_WORD_COOLDOWN_MS", "2000")
)  # Cooldown between detections (ms)
WAKE_WORD_LOG_SCORES = os.getenv("WAKE_WORD_LOG_SCORES", "false").lower() in {
    "1",
    "true",
    "yes",
    "on",
}
WAKE_WORD_SCORE_LOG_INTERVAL_MS = int(
    os.getenv("WAKE_WORD_SCORE_LOG_INTERVAL_MS", "1000")
)
# Custom wake word (requires training - advanced feature)
WAKE_WORD_CUSTOM = os.getenv(
    "WAKE_WORD_CUSTOM", ""
)  # Custom wake word (e.g., "hey buddy")
# "tflite" uses ~100MB less RAM than "onnx"; fall back to "onnx" if tflite not available
OWW_INFERENCE_FRAMEWORK = os.getenv("OWW_INFERENCE_FRAMEWORK", "tflite")


# STT settings (faster-whisper)
# Use "tiny" to save ~300MB RAM vs "base". Accuracy is nearly identical for short commands.
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "tiny")
try:
    import torch

    WHISPER_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    WHISPER_DEVICE = "cpu"

WHISPER_COMPUTE_TYPE = "float16" if WHISPER_DEVICE == "cuda" else "int8"

# VAD settings (Silero)
VAD_THRESHOLD = float(
    os.getenv("VAD_THRESHOLD", "0.6")
)  # Higher = less sensitive to background noise (0.3-0.9 range)
VAD_MIN_SPEECH_MS = int(
    os.getenv("VAD_MIN_SPEECH_MS", "300")
)  # Min speech duration to trigger (ms)
SILENCE_DURATION_MS = int(
    os.getenv("SILENCE_DURATION_MS", "2000")
)  # Stop listening after N ms of silence
MIN_SPEECH_DURATION_MS = int(
    os.getenv("MIN_SPEECH_DURATION_MS", "250")
)  # Minimum speech to accept
MIN_COMMAND_CONFIDENCE = float(os.getenv("MIN_COMMAND_CONFIDENCE", "0.55"))

# Session mode (continuous voice chat)
SESSION_ENABLED = os.getenv("SESSION_ENABLED", "true").strip().lower() == "true"
SESSION_IDLE_TIMEOUT = float(os.getenv("SESSION_IDLE_TIMEOUT", "15"))  # seconds of silence before ending session
INTERRUPT_THRESHOLD = float(os.getenv("INTERRUPT_THRESHOLD", "0.03"))  # RMS energy threshold for interruption
INTERRUPT_MS = int(os.getenv("INTERRUPT_MS", "300"))  # ms of speech to trigger interruption

# LLM settings
# Priority: local first (offline-capable) then cloud fallbacks
_OLLAMA_MODELS_RAW = os.getenv(
    "OLLAMA_MODELS",
    os.getenv("OLLAMA_MODEL", "phi4-mini:latest,qwen3.5:4b-q4_K_M"),
)
OLLAMA_MODELS = [
    model.strip() for model in _OLLAMA_MODELS_RAW.split(",") if model.strip()
]
OLLAMA_MODEL = OLLAMA_MODELS[0] if OLLAMA_MODELS else "phi4-mini:latest"
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")

# LLM priority mode: "local_first" = Ollama primary, cloud fallback | "cloud_first" = cloud primary | "online_only" = skip Ollama
LLM_PRIORITY_MODE = os.getenv("LLM_PRIORITY_MODE", "local_first")
OLLAMA_KEEP_ALIVE = os.getenv(
    "OLLAMA_KEEP_ALIVE", "5m"
)  # Keep model loaded for responsiveness
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "meta-llama/llama-3.3-70b-instruct:free"
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct"  # Powerful model
OPENCODE_API_KEY = os.getenv("OPENCODE_API_KEY", "")
OPENCODE_BASE_URL = os.getenv("OPENCODE_BASE_URL", "https://opencode.ai/zen/v1")
OPENCODE_MODEL = os.getenv("OPENCODE_MODEL", "deepseek-v4-flash-free")

# Dynamic tool discovery keeps tool context small:
# model sees only search_tools first, then gets a tiny relevant subset.
DYNAMIC_TOOL_DISCOVERY_ENABLED = os.getenv(
    "DYNAMIC_TOOL_DISCOVERY_ENABLED", "true"
).lower() in {"1", "true", "yes"}
DYNAMIC_TOOL_DISCOVERY_TOP_K = int(os.getenv("DYNAMIC_TOOL_DISCOVERY_TOP_K", "8"))

# FreeLLMAPI proxy (OpenAI-compatible proxy)
FREELLMAPI_API_KEY = os.getenv("FREELLMAPI_API_KEY", "")
FREELLMAPI_BASE_URL = os.getenv("FREELLMAPI_BASE_URL", "http://127.0.0.1:3001/v1")
FREELLMAPI_MODEL = os.getenv("FREELLMAPI_MODEL", "auto")

# LM Studio settings (local OpenAI-compatible API)
LMSTUDIO_HOST = os.getenv("LMSTUDIO_HOST", "http://localhost:1234/v1")
LMSTUDIO_MODEL = os.getenv("LMSTUDIO_MODEL", "falcon-h1r-7b")  # Model name in LM Studio

# Service Keys
OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY", "")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY", "")
NEWSAPI_API_KEY = os.getenv("NEWSAPI_API_KEY", "")

# Spotify API (for background control)
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")
SPOTIFY_REDIRECT_URI = os.getenv(
    "SPOTIFY_REDIRECT_URI", "http://127.0.0.1:8888/callback"
)

# TTS settings
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")
TTS_RATE = "+0%"
TTS_PITCH = "+0Hz"
TTS_USE_OFFLINE = os.getenv("TTS_USE_OFFLINE", "true").lower() == "true"
TTS_OFFLINE_VOICE = os.getenv("TTS_OFFLINE_VOICE", "en_GB-alan-medium")
PIPER_VOICE_PATH = os.getenv(
    "PIPER_VOICE_PATH",
    str(
        BASE_DIR
        / "data"
        / "models"
        / "piper"
        / "alan"
        / "medium"
        / "en_GB-alan-medium.onnx"
    ),
)  # Path to .onnx model file

# MCP Server Configuration - Keep only essential servers
# Unused: http, workflow, google, browser (covered by browser_skill)
MCP_SERVERS = {
    "desktop_commander": {
        "command": "node",
        "args": ["mcp-tools/DesktopCommanderMCP/dist/index.js", "--no-onboarding"],
    },
    "planner": {"command": "python3", "args": ["mcp-tools/planner-mcp/server.py"]},
    "router": {"command": "python3", "args": ["mcp-tools/router-mcp/server.py"]},
    "memory": {"command": "python3", "args": ["mcp-tools/memory-mcp/server.py"]},
    # DISABLED (not essential or covered by skills):
    # "workflow": {...},   # Rarely used
    # "browser": {...},   # Covered by browser_skill
    # "http": {...},    # Not used
    # "google": {...},  # Covered by browser
}

# Assistant personality
ASSISTANT_NAME = "Buddy"

# Dashboard / user identity
USER_NAME = os.getenv("USER_NAME", "sir")

# Core Skills (active skills - keep small for maintainability)
CORE_SKILLS = [
    "time",  # Time queries
    "weather",  # Weather info
    "calendar",  # Calendar events
    "reminder",  # Reminders
    "browser",  # Web browsing/automation
    "system",  # System control
    "memory",  # Memory management
]

# Archived skills (loaded but disabled)
ARCHIVED_SKILLS = [
    "waifu",  # Visual avatar - fun feature
    "feedback",  # Not implemented
    "registry",  # Fragile Windows ops
    "news",  # Rarely used
]

# Interaction / Presence behavior
# Default to push-to-talk style startup to avoid permanently holding the mic.
WAKE_WORD_STARTUP_ENABLED = os.getenv("WAKE_WORD_STARTUP_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}
ORB_IDLE_HIDE_AFTER = float(os.getenv("ORB_IDLE_HIDE_AFTER", "4.0"))
MIC_IDLE_RELEASE_AFTER = float(os.getenv("MIC_IDLE_RELEASE_AFTER", "6.0"))
LOW_MEMORY_MODE = os.getenv("LOW_MEMORY_MODE", "false").lower() in {"1", "true", "yes"}
LOW_MEMORY_UNLOAD_DELAY_SEC = float(os.getenv("LOW_MEMORY_UNLOAD_DELAY_SEC", "2.0"))
OLLAMA_KEEP_ALIVE = os.getenv("OLLAMA_KEEP_ALIVE", "0s" if LOW_MEMORY_MODE else "5m")

# Long-term Memory Settings
ENABLE_LONG_TERM_MEMORY = True
MEMORY_DB_PATH = "data/memory.db"  # Path to long-term memory database
MEMORY_MIN_CONFIDENCE = 0.7  # Minimum confidence for memory retrieval
MEMORY_MAX_RESULTS = 5  # Maximum memories to include in context
# Uses Ollama for embeddings (fast, local, ~0 extra RAM). Falls back to keyword search.
ENABLE_EMBEDDINGS = os.getenv("ENABLE_EMBEDDINGS", "true").lower() in {
    "1",
    "true",
    "yes",
}

# Proactive Intelligence Settings
PROACTIVE_SETTINGS = {
    "ENABLED": True,
    "CHECK_INTERVAL": 60,  # Check every 60 seconds
    "BATTERY_THRESHOLD": 20,  # Warn if battery < 20%
    "IDLE_THRESHOLD": 3600,  # 1 hour in seconds
    "MORNING_HOUR": 8,  # Morning greeting start hour
    "NIGHT_HOUR": 22,  # Night mode suggestion hour
    # Additional proactive features
    "LOW_MEMORY_WARNING_MB": 512,  # Warn if available RAM < 512MB
    "IDLE_GREETING": True,  # Greet after idle period
    "CONTEXT_AWARENESS": True,  # Remember recent topics
    "HELPFUL_SUGGESTIONS": True,  # Offer helpful suggestions
}

# Desktop Awareness Settings
DESKTOP_AWARENESS_ENABLED = os.getenv("DESKTOP_AWARENESS_ENABLED", "false").lower() in {
    "1",
    "true",
    "yes",
}
DESKTOP_AWARENESS_INTERVAL = float(os.getenv("DESKTOP_AWARENESS_INTERVAL", "10"))
DESKTOP_AWARENESS_OCR = os.getenv("DESKTOP_AWARENESS_OCR", "true").lower() in {
    "1",
    "true",
    "yes",
}
DESKTOP_AWARENESS_HISTORY = int(os.getenv("DESKTOP_AWARENESS_HISTORY", "3"))

# Authority Gating Settings
AUTHORITY_GATE_ENABLED = os.getenv("AUTHORITY_GATE_ENABLED", "true").lower() in {
    "1",
    "true",
    "yes",
}
AUTHORITY_MIN_LEVEL = int(
    os.getenv("AUTHORITY_MIN_LEVEL", "3")
)  # 1=LOW, 2=MEDIUM, 3=HIGH, 4=CRITICAL


# ---------------------------------------------------------------------------
# API token bootstrap + bind-host safety guard (shared by both HTTP servers)
# ---------------------------------------------------------------------------

_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "localhost"}


def get_api_token() -> str:
    """Return BUDDY_API_TOKEN from env, else load/create data/api_token.

    Creates the file with secrets.token_urlsafe(32) on first call.
    Logs only the PATH — never the token value.
    """
    env_token = os.getenv("BUDDY_API_TOKEN", "")
    if env_token:
        return env_token

    token_path = BASE_DIR / "data" / "api_token"
    try:
        existing = token_path.read_text(encoding="utf-8").strip()
    except OSError:
        existing = ""
    if existing:
        return existing

    token_path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    # Owner-only permissions where the OS honours them (no-op on Windows ACLs).
    fd = os.open(str(token_path), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(token)
    logger.info("API token file ready at %s", token_path)
    return token


def assert_safe_bind(host: str) -> None:
    """Refuse non-loopback binds unless BUDDY_API_TOKEN is explicitly set."""
    host_norm = str(host or "").strip().lower()
    if host_norm in _LOOPBACK_HOSTS:
        return
    if os.getenv("BUDDY_API_TOKEN"):
        return
    raise RuntimeError(
        f"Refusing to bind non-loopback host '{host}' without BUDDY_API_TOKEN set. "
        "Set BUDDY_API_TOKEN or keep the server on 127.0.0.1."
    )
