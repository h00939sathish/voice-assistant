"""
Configuration module for Buddy Voice Assistant
"""
import os
from pathlib import Path
from dotenv import load_dotenv

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
CHUNK_SIZE = 512  # ~32ms at 16kHz

# Wake word settings
WAKE_WORD_MODEL = "hey_jarvis"  # Built-in openWakeWord model
WAKE_WORD_THRESHOLD = float(os.getenv("WAKE_WORD_THRESHOLD", "0.4"))

# Porcupine settings
PICOVOICE_ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY", "")
# Path to custom .ppn file (relative to project root)
PORCUPINE_KEYWORD_PATH = BASE_DIR / "HEY-JARVIS_en_windows_v4_0_0" / "HEY-JARVIS_en_windows_v4_0_0.ppn"

# STT settings (faster-whisper)
WHISPER_MODEL = os.getenv("WHISPER_MODEL", "base")
try:
    import torch
    WHISPER_DEVICE = "cuda" if torch.cuda.is_available() else "cpu"
except ImportError:
    WHISPER_DEVICE = "cpu"
    
WHISPER_COMPUTE_TYPE = "float16" if WHISPER_DEVICE == "cuda" else "int8"

# VAD settings (Silero)
VAD_THRESHOLD = 0.5
SILENCE_DURATION_MS = 700  # Stop listening after 700ms of silence
MIN_SPEECH_DURATION_MS = 250  # Minimum speech to accept

# LLM settings
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "llama3.2")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
OPENROUTER_MODEL = "google/gemini-2.0-flash-exp:free"  # Reliable free model via OpenRouter
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
NVIDIA_MODEL = "meta/llama-3.1-70b-instruct" # Powerful model

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
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI", "http://localhost:8888/callback")

# TTS settings
TTS_VOICE = os.getenv("TTS_VOICE", "en-US-AriaNeural")
TTS_RATE = "+0%"
TTS_PITCH = "+0Hz"

# MCP Server Configuration
# Keys are the names you use to address them (e.g. "ask desktop commander")
MCP_SERVERS = {
    "desktop_commander": {
        "command": "node", 
        "args": ["mcp-tools/DesktopCommanderMCP/dist/index.js"]
    },
    # "context7": { ... } # User needs to provide path
    "github": {
        "command": "uvx",
        "args": ["mcp-server-github"],
        "env": {
            **os.environ,
            "GITHUB_PERSONAL_ACCESS_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", ""),
            "GITHUB_TOKEN": os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN", "") # Try both common names
        }
    }
}

# Assistant personality
ASSISTANT_NAME = "Buddy"

# Long-term Memory Settings
ENABLE_LONG_TERM_MEMORY = True
MEMORY_DB_PATH = "data/memory.db"  # Path to long-term memory database
MEMORY_MIN_CONFIDENCE = 0.7  # Minimum confidence for memory retrieval
MEMORY_MAX_RESULTS = 5  # Maximum memories to include in context

# Proactive Intelligence Settings
PROACTIVE_SETTINGS = {
    "ENABLED": True,
    "CHECK_INTERVAL": 60,  # Check every 60 seconds
    "BATTERY_THRESHOLD": 20,  # Warn if battery < 20%
    "IDLE_THRESHOLD": 3600,  # 1 hour in seconds
    "MORNING_HOUR": 8,  # Morning greeting start hour
    "NIGHT_HOUR": 22,   # Night mode suggestion hour
}
