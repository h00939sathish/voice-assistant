import logging
import threading
from dataclasses import dataclass
from threading import Lock
from typing import Any

from assistant.audio_manager import AudioManager
from assistant.conversation_memory import ConversationMemory
from assistant.di import container
from assistant.events import EventBus, SubsystemStateEvent
from assistant.interfaces import IAudioManager, ILLMProvider, ISTTProvider, ITTSProvider
from assistant.llm_router import LLMRouter
from assistant.long_term_memory import LongTermMemory
from assistant.skill_router import SkillRouter
from assistant.stt import SpeechToText
from assistant.tts import TextToSpeech
from config import (
    LOW_MEMORY_MODE,
)

logger = logging.getLogger("app_init")


@dataclass
class ComponentHandle:
    wake_detector: Any = None
    task_executor: Any = None

    def __post_init__(self) -> None:
        self._lock = Lock()

    def set_wake_detector(self, value: Any) -> None:
        with self._lock:
            self.wake_detector = value

    def set_task_executor(self, value: Any) -> None:
        with self._lock:
            self.task_executor = value


def setup_dependencies() -> dict:
    """Setup dependency injection container and create instances."""
    container.register(IAudioManager, AudioManager)
    container.register(ISTTProvider, SpeechToText)
    container.register(ITTSProvider, TextToSpeech)

    memory = ConversationMemory()
    ltm = LongTermMemory()

    llm = LLMRouter(conversation_memory=memory, long_term_memory=ltm)
    if hasattr(llm, "get_tool_runner"):
        llm.get_tool_runner().set_allow_terminal_confirmation(False)
    container.register(ILLMProvider, llm)

    skill_router = SkillRouter(
        llm_router=llm,
        tts=container.resolve(ITTSProvider),
        tool_runner=llm.get_tool_runner() if hasattr(llm, "get_tool_runner") else None,
    )
    container.register(SkillRouter, skill_router)

    return {
        "audio": container.resolve(IAudioManager),
        "stt": container.resolve(ISTTProvider),
        "tts": container.resolve(ITTSProvider),
        "llm": container.resolve(ILLMProvider),
        "skill_router": container.resolve(SkillRouter),
        "event_bus": container.resolve(EventBus),
    }


def init_audio_system(
    audio: IAudioManager, wake_word_enabled: bool, event_bus: EventBus
) -> None:
    """Initialize audio system based on wake word mode."""
    if wake_word_enabled:
        if not audio.is_stream_active:
            audio.start_stream()
        if not audio.is_recording:
            audio.start_recording()
        logger.info("   🎙️ Wake-word mode enabled (continuous listening)")
        event_bus.publish(
            SubsystemStateEvent(
                subsystem="mic",
                state="healthy",
                detail="continuous listening",
            )
        )
    else:
        try:
            audio.stop_recording()
            audio.stop_stream()
        except Exception:
            pass
        logger.info("   🎙️ Push-to-talk mode enabled (Ctrl+Space / Win+S)")
        event_bus.publish(
            SubsystemStateEvent(
                subsystem="mic",
                state="degraded",
                detail="push-to-talk standby",
            )
        )

    if LOW_MEMORY_MODE:
        logger.info(
            "   Low-memory mode enabled: wake-word stays active, STT is loaded after wake and unloaded on idle"
        )


def preload_components(
    stt: ISTTProvider,
    llm: ILLMProvider,
    skill_router: SkillRouter,
    event_bus: EventBus,
    low_memory_mode: bool,
) -> ComponentHandle:
    """Preload heavy components in background thread. Returns a live component handle."""
    handle = ComponentHandle()

    def preload_heavy_components():
        logger.info("   🔄 Background: Starting sequential preloading...")

        if low_memory_mode:
            logger.info("   Low-memory mode active: deferring STT load until wake")
            event_bus.publish(
                SubsystemStateEvent(
                    subsystem="stt", state="initializing", detail="deferred"
                )
            )
        else:
            try:
                logger.info("   🔄 Loading STT...")
                stt.load_models()
                logger.info("   ✅ STT ready")
                event_bus.publish(SubsystemStateEvent(subsystem="stt", state="healthy"))
            except Exception as e:
                logger.error(f"   ❌ STT load failed: {e}")
                event_bus.publish(
                    SubsystemStateEvent(subsystem="stt", state="down", detail=str(e))
                )

        try:
            from assistant.wake_word import WakeWordDetector

            wake_detector = WakeWordDetector()
            handle.set_wake_detector(wake_detector)

            logger.info("   🔄 Loading Wake Word...")
            wake_detector.load_model()
            if getattr(wake_detector, "_is_loaded", False):
                logger.info("   ✅ Wake Word ready")
                event_bus.publish(
                    SubsystemStateEvent(subsystem="wake_word", state="healthy")
                )
            else:
                logger.warning("   ⚠️ Wake Word not available after preload")
                event_bus.publish(
                    SubsystemStateEvent(
                        subsystem="wake_word",
                        state="down",
                        detail="all wake word engines failed to load",
                    )
                )
        except Exception as e:
            logger.error(f"   ❌ Wake Word load failed: {e}")
            event_bus.publish(
                SubsystemStateEvent(subsystem="wake_word", state="down", detail=str(e))
            )

        try:
            logger.info("   🔄 Loading Skills...")
            skill_router.load_skills()
            logger.info("   ✅ Skills ready")
            event_bus.publish(SubsystemStateEvent(subsystem="skills", state="healthy"))
        except Exception as e:
            logger.error(f"   ❌ Skills load failed: {e}")
            event_bus.publish(
                SubsystemStateEvent(subsystem="skills", state="down", detail=str(e))
            )

        logger.info("   🏁 Background: Preloading sequence finished")

        try:
            from assistant.task_executor import TaskExecutor

            tool_runner = (
                llm.get_tool_runner()
                if hasattr(llm, "get_tool_runner")
                else llm._tool_runner
            )
            task_executor = TaskExecutor(tool_runner)
            handle.set_task_executor(task_executor)
            pending = task_executor.get_pending_tasks()
            if pending:
                logger.info(f"   📋 Resuming {len(pending)} pending task(s)")
            llm.set_task_executor(task_executor)
            logger.info("   ✅ TaskExecutor ready")
        except Exception as e:
            logger.warning(f"   ⚠️ TaskExecutor init failed: {e}")

    threading.Thread(target=preload_heavy_components, daemon=True).start()

    return handle


def init_proactive_engine():
    """Initialize proactive engine if available."""
    try:
        from assistant.proactive_engine import ProactiveEngine

        return ProactiveEngine()
    except ImportError:
        logger.warning("⚠️ Proactive Engine could not be loaded")
        return None
    except Exception as e:
        logger.warning(f"⚠️ Proactive Error: {e}")
        return None


def start_dashboard(
    dashboard_host: str = "127.0.0.1", dashboard_port: int = 5050
) -> bool:
    """Start the dashboard web server. Returns True if successful."""
    try:
        import sys as _sys
        from pathlib import Path

        _sys.path.insert(0, str(Path(__file__).parent.parent))
        import dashboard.app as _dash_app

        _dash_thread = threading.Thread(
            target=_dash_app.run_server,
            kwargs={"host": dashboard_host, "port": dashboard_port},
            daemon=True,
            name="BuddyDashboard",
        )
        _dash_thread.start()
        logger.info(
            f"   🌐 Dashboard started at http://{dashboard_host}:{dashboard_port}"
        )
        return True
    except Exception as e:
        logger.warning(f"   ⚠️ Dashboard failed to start: {e}")
        return False
