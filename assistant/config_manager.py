import logging
import os
import sys
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Setup basic logging
logger = logging.getLogger("AI_Assistant.Config")

load_dotenv()


class Config:
    """Enhanced configuration class with better error handling and validation"""

    # ================== Paths (Centralized) ==================
    BASE_DIR = Path(__file__).parent.parent.absolute()
    MODELS_DIR = BASE_DIR / "models"
    CACHE_DIR = BASE_DIR / os.getenv("CACHE_DIR", "cache")
    LOGS_DIR = BASE_DIR / os.getenv("LOGS_DIR", "logs")
    SKILLS_DIR = BASE_DIR / "skills"
    BACKUPS_DIR = BASE_DIR / "backups"
    TEMP_DIR = BASE_DIR / "temp"

    # YAML Registries
    MODEL_REGISTRY_PATH = BASE_DIR / "jarvis_model_registry.yaml"
    SETTINGS_PATH = BASE_DIR / "settings.yaml"

    # Load YAMLs
    MODELS_CONFIG = {}
    SETTINGS_CONFIG = {}

    try:
        if MODEL_REGISTRY_PATH.exists():
            with open(MODEL_REGISTRY_PATH) as f:
                MODELS_CONFIG = yaml.safe_load(f) or {}

        if SETTINGS_PATH.exists():
            with open(SETTINGS_PATH) as f:
                SETTINGS_CONFIG = yaml.safe_load(f) or {}
    except ImportError:
        logger.warning("⚠️ PyYAML not installed. Using defaults.")
    except Exception as e:
        logger.error(f"❌ Config Load Error: {e}")

    # Database
    DB_FILE = BASE_DIR / os.getenv("DB_FILE", "assistant_memory.db")

    # Vosk Model (Legacy)
    VOSK_MODEL_PATH = MODELS_DIR / "vosk-model-small-en-us-0.15"

    # ================== Core Configuration ==================
    LOCAL_ONLY = bool(os.getenv("LOCAL_ONLY", "").lower() in {"1", "true", "yes"})

    # ================== API Keys & Credentials ==================
    OPENWEATHERMAP_API_KEY = os.getenv("OPENWEATHERMAP_API_KEY")
    ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
    NEWSAPI_API_KEY = os.getenv("NEWSAPI_API_KEY")
    SLACK_API_TOKEN = os.getenv("SLACK_API_TOKEN")
    GROQ_API_KEY = os.getenv("GROQ_API_KEY")

    # ================== Web Agent Configuration ==================
    WEB_AGENT_ENABLED = bool(
        os.getenv("WEB_AGENT_ENABLED", "true").lower() in {"1", "true", "yes"}
    )
    WEB_AGENT_MODE = os.getenv("WEB_AGENT_MODE", "auto")
    WEB_AGENT_BROWSER = os.getenv("WEB_AGENT_BROWSER", "chromium")
    WEB_AGENT_HEADLESS = bool(
        os.getenv("WEB_AGENT_HEADLESS", "true").lower() in {"1", "true", "yes"}
    )

    # ================== System Configuration ==================
    GAMING_MODE = bool(
        os.getenv("GAMING_MODE", "false").lower() in {"1", "true", "yes"}
    )

    # ================== Helpers ==================
    @classmethod
    def setup_directories(cls):
        """Setup required directories with error handling"""
        directories = [
            cls.CACHE_DIR,
            cls.LOGS_DIR,
            cls.SKILLS_DIR,
            cls.BACKUPS_DIR,
            cls.TEMP_DIR,
        ]
        for directory in directories:
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                logger.error(f"❌ Failed to create directory {directory}: {e}")

    @classmethod
    def get_system_info(cls):
        """Get system information for optimization"""
        try:
            import psutil

            return {
                "cpu_count": psutil.cpu_count(),
                "memory_total_gb": psutil.virtual_memory().total / (1024**3),
                "platform": sys.platform,
            }
        except ImportError:
            return {}


# Initialize
try:
    Config.setup_directories()
except Exception as e:
    logger.error(f"Failed to initialize configuration: {e}")
