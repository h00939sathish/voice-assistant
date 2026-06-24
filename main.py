"""
Buddy Voice Assistant - Main Application (Desktop Mode)
Uses PyQt6 for Siri-like Orb Overlay and pystray for System Tray.
"""

import asyncio
import os
import random
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

if os.name == "nt":
    try:
        _cwd = os.getcwd()
        if _cwd.startswith("\\\\?\\"):
            os.chdir(_cwd[4:])
        sys.path = [
            p[4:] if isinstance(p, str) and p.startswith("\\\\?\\") else p
            for p in sys.path
        ]
    except Exception:
        pass

if sys.stdout and getattr(sys.stdout, "encoding", "").lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if sys.stderr and getattr(sys.stderr, "encoding", "").lower() != "utf-8":
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).parent))

from assistant.app_init import (
    init_audio_system,
    init_proactive_engine,
    preload_components,
    setup_dependencies,
    start_dashboard,
)
from assistant.cli_parser import parse_args
from assistant.dashboard_bridge import DashboardBridge
from assistant.events import (
    ConfirmationEvent,
    ResponseEvent,
    StateChangeEvent,
    StatusEvent,
    SubsystemStateEvent,
    TranscriptionEvent,
)
from assistant.health_monitor import get_monitor
from assistant.logger import get_logger, setup_logger
from assistant.orb_overlay import OrbOverlay, OrbState
from assistant.state_machine import (
    AssistantState,
    explain_invalid_transition,
    is_valid_transition,
)
from config import (
    ASSISTANT_NAME,
    INTERRUPT_MS,
    INTERRUPT_THRESHOLD,
    LOW_MEMORY_MODE,
    LOW_MEMORY_UNLOAD_DELAY_SEC,
    MIC_IDLE_RELEASE_AFTER,
    MIN_COMMAND_CONFIDENCE,
    ORB_IDLE_HIDE_AFTER,
    SESSION_ENABLED,
    SESSION_IDLE_TIMEOUT,
    SOUNDS_DIR,
    WAKE_WORD_STARTUP_ENABLED,
)
from gui.tray import SystemTrayApp
from assistant.vad import InterruptionVAD

logger = get_logger("main")


class VoiceAssistant:
    """Main voice assistant application"""

    FOLLOWUP_PHRASES: list[str] = [
        "what would you like",
        "what should i",
        "would you like me to",
        "anything else",
        "what else",
        "tell me more",
        "which one",
        "please specify",
        "can you clarify",
    ]

    COMMAND_ALIASES: dict[str, str] = {
        "play music": "spotify play",
        "pause music": "spotify pause",
        "next song": "spotify next",
        "previous song": "spotify previous",
        "stop music": "spotify pause",
        "what time": "what time is it",
        "tell me the time": "what time is it",
        "what's the date": "what date",
        "set a reminder": "create reminder",
        "remind me": "create reminder",
    }

    def __init__(self, audio, stt, tts, llm, skill_router, event_bus) -> None:
        self.state: AssistantState = AssistantState.STARTING
        self._ready = threading.Event()
        self._running: bool = False
        self._wake_triggered: bool = False
        self._last_activity: float = time.time()
        self._ambient_timeout: float = 30.0
        self._keyboard_available: bool = False
        self.monitor = None
        self.ui_callback: Callable | None = None
        self.memory = None
        self.long_term_memory = None
        self.proactive_engine = None
        self.wake_detector = None
        self.orb = None
        self._wake_word_enabled: bool = WAKE_WORD_STARTUP_ENABLED
        if LOW_MEMORY_MODE:
            self._wake_word_enabled = True
        self._idle_since: float = time.time()
        self._idle_hide_after: float = ORB_IDLE_HIDE_AFTER
        self._mic_idle_release_after: float = MIC_IDLE_RELEASE_AFTER
        self._in_session: bool = False
        self._session_enabled: bool = SESSION_ENABLED
        self._session_idle_timeout: float = SESSION_IDLE_TIMEOUT
        self._interrupt_threshold: float = INTERRUPT_THRESHOLD
        self._interrupt_ms: int = INTERRUPT_MS
        self._followup_count: int = 0
        self._orb_is_hidden: bool = True
        self._mic_released: bool = True
        self._low_memory_mode: bool = LOW_MEMORY_MODE
        self._low_memory_unload_delay_sec: float = max(0.0, LOW_MEMORY_UNLOAD_DELAY_SEC)
        self._stt_unload_timer: threading.Timer | None = None
        self._stt_unload_lock = threading.Lock()

        self.audio = audio
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.skill_router = skill_router
        self.bus = event_bus

        self.task_executor = None
        self.component_handle = None
        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._loop_thread: threading.Thread | None = None

        from assistant.conversation_memory import ConversationMemory
        from assistant.long_term_memory import LongTermMemory

        self.memory = ConversationMemory()
        self.long_term_memory = LongTermMemory()

        logger.info(f"  🤖 {ASSISTANT_NAME} Voice Assistant (Orb Mode)")

    def set_ui_callback(self, callback: Callable) -> None:
        self.ui_callback = callback

    def _ensure_mic_active(self) -> None:
        try:
            if not self.audio.is_stream_active:
                self.audio.start_stream()
            if not self.audio.is_recording:
                self.audio.start_recording()
            self._mic_released = False
        except Exception as e:
            logger.warning(f"Failed to activate microphone: {e}")

    def _release_microphone(self) -> None:
        if self._mic_released:
            return
        try:
            self.audio.stop_recording()
            self.audio.stop_stream()
            self._mic_released = True
            logger.debug("🎙️ Microphone released (idle mode)")
        except Exception as e:
            logger.warning(f"Failed to release microphone: {e}")

    def _cancel_stt_unload(self) -> None:
        if not self._low_memory_mode:
            return
        with self._stt_unload_lock:
            if self._stt_unload_timer is not None:
                self._stt_unload_timer.cancel()
                self._stt_unload_timer = None

    def _schedule_stt_unload(self) -> None:
        if not self._low_memory_mode:
            return
        self._cancel_stt_unload()

        def _unload_if_idle():
            try:
                if self.state == AssistantState.IDLE and hasattr(
                    self.stt, "unload_models"
                ):
                    self.stt.unload_models()
                    logger.debug("Low-memory mode: STT unloaded while idle")
            except Exception as e:
                logger.debug(f"Low-memory mode: STT unload skipped ({e})")
            finally:
                with self._stt_unload_lock:
                    self._stt_unload_timer = None

        if self._low_memory_unload_delay_sec <= 0:
            threading.Thread(target=_unload_if_idle, daemon=True).start()
            return

        timer = threading.Timer(self._low_memory_unload_delay_sec, _unload_if_idle)
        timer.daemon = True
        with self._stt_unload_lock:
            self._stt_unload_timer = timer
        timer.start()

    def _warm_stt_async(self) -> None:
        if not self._low_memory_mode:
            return
        if hasattr(self.stt, "reload_if_needed"):
            threading.Thread(target=self.stt.reload_if_needed, daemon=True).start()

    def _apply_aliases(self, text: str) -> str:
        lower_text = text.lower().strip()
        for alias, command in self.COMMAND_ALIASES.items():
            if alias in lower_text:
                logger.debug(f"Applied alias: '{alias}' -> '{command}'")
                return command
        return text

    def _start_keyboard_listener(self) -> None:
        try:
            import keyboard

            def on_hotkey():
                if not self._wake_triggered:
                    logger.info("   ⌨️ Hotkey triggered wake")
                    self._wake_triggered = True
                    self._ensure_mic_active()
                    self._orb_is_hidden = False
                    if self.orb:
                        self.orb.set_state(OrbState.LISTENING.value)

            def toggle_wake_word():
                enabled = self.set_wake_word_enabled(not self._wake_word_enabled)
                status = "ON" if enabled else "OFF"
                logger.info(f"   ⌨️ Wake word toggled: {status}")
                asyncio.run_coroutine_threadsafe(
                    self.tts.speak_streaming(f"Wake word {status}"), self._loop
                )

            keyboard.add_hotkey("ctrl + space", on_hotkey, suppress=True)
            keyboard.add_hotkey("caps lock", on_hotkey, suppress=True)
            keyboard.add_hotkey("windows + s", on_hotkey, suppress=True)

            wake_word_hotkey = "alt + w"
            try:
                keyboard.add_hotkey(wake_word_hotkey, toggle_wake_word)
            except Exception as e:
                logger.warning(
                    "Failed to register wake word toggle hotkey '%s': %s",
                    wake_word_hotkey,
                    e,
                )

            def toggle_history():
                logger.info("   ⌨️ Hotkey: Toggle History")

            keyboard.add_hotkey("windows + h", toggle_history)

            self._keyboard_available = True
            logger.info(
                "   ⌨️ Keyboard listener started (Ctrl+Space, CapsLock, Win+S, Alt+W, Win+H)"
            )
        except ImportError:
            logger.warning("   ⌨️ keyboard package not installed. Hotkeys disabled.")
        except Exception as e:
            logger.warning(f"   ⌨️ Keyboard listener failed: {e}")

    def set_wake_word_enabled(self, enabled: bool) -> bool:
        """Enable or disable continuous wake-word listening."""
        self._wake_word_enabled = bool(enabled)
        if self._wake_word_enabled:
            self._ensure_mic_active()
        else:
            self._release_microphone()
            logger.info("   🎙️ Microphone released")

        if self.orb:
            if self._wake_word_enabled:
                self.orb.set_state(OrbState.IDLE.value)
                self._orb_is_hidden = False
            else:
                self.orb.set_state(OrbState.HIDDEN.value)
                self._orb_is_hidden = True

        return self._wake_word_enabled

    def initialize(self) -> None:
        logger.info("📦 Initializing system (Background Preloading Enabled)...")

        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()

        init_audio_system(self.audio, self._wake_word_enabled, self.bus)

        if self._low_memory_mode:
            logger.info(
                "   Low-memory mode enabled: wake-word stays active, STT is loaded after wake and unloaded on idle"
            )

        self.component_handle = preload_components(
            self.stt,
            self.llm,
            self.skill_router,
            self.bus,
            self._low_memory_mode,
        )
        self._sync_background_components()

        self.proactive_engine = init_proactive_engine()
        if self.proactive_engine and hasattr(self.proactive_engine, "memory_system"):
            self.proactive_engine.memory_system = self.long_term_memory

        self.monitor = get_monitor()
        logger.info("🚀 Buddy core initialized!")
        self.monitor.start()
        self.bus.publish(
            SubsystemStateEvent(
                subsystem="llm", state="healthy", detail="router initialized"
            )
        )
        self.bus.publish(
            SubsystemStateEvent(
                subsystem="memory", state="healthy", detail="memory systems ready"
            )
        )
        self.bus.publish(
            SubsystemStateEvent(
                subsystem="scheduler", state="healthy", detail="scheduler available"
            )
        )

        self._start_keyboard_listener()

    def _transition(self, new_state: AssistantState) -> None:
        if self.state != new_state:
            old_state_name = self.state.name
            new_state_name = new_state.name

            if not is_valid_transition(self.state, new_state):
                reason = explain_invalid_transition(self.state, new_state)
                logger.warning(f"   ⚠️ {reason}")
                return

            logger.debug(f"[{old_state_name}] → [{new_state_name}]")

            self.bus.publish(
                StateChangeEvent(old_state=old_state_name, new_state=new_state_name)
            )

            self.state = new_state
            self._last_activity = time.time()

            if self._low_memory_mode:
                if new_state == AssistantState.IDLE:
                    self._schedule_stt_unload()
                else:
                    self._cancel_stt_unload()

            if self.ui_callback:
                self.ui_callback(new_state_name)

    def trigger_wake(self) -> None:
        self._wake_triggered = True

    async def run(self) -> None:
        self._running = True
        crash_count = 0
        last_crash_time = 0

        if self.state == AssistantState.STARTING:
            self._transition(AssistantState.IDLE)
            self._ready.set()

        logger.info("🛡️ Watchdog active")

        while self._running:
            try:
                await self._run_loop()
            except asyncio.CancelledError:
                break
            except Exception as e:
                current_time = time.time()
                if current_time - last_crash_time > 60:
                    crash_count = 0

                crash_count += 1
                last_crash_time = current_time

                logger.critical(f"🔥 Critical Failure ({crash_count}/3): {e}")

                from assistant.events import ErrorEvent

                self.bus.publish(ErrorEvent(error=e, component="VoiceAssistant"))
                self._transition(AssistantState.ERROR)

                if crash_count >= 3:
                    logger.critical("❌ Too many crashes. Aborting.")
                    self._running = False
                    break

                logger.info("🔄 Restarting in 2 seconds...")
                await asyncio.sleep(2)

        self.shutdown()

    def _enter_listening(self):
        self._ensure_mic_active()
        self._warm_stt_async()
        self._idle_since = time.time()
        self._followup_count = 0
        self._orb_is_hidden = False
        self._transition(AssistantState.LISTENING)
        if self.orb:
            self.orb.set_state(OrbState.LISTENING.value)

    def _enter_idle(self):
        self._followup_count = 0
        self._idle_since = time.time()
        self._transition(AssistantState.IDLE)

    _GREETINGS = [
        "Yes?",
        "How can I help?",
        "I'm listening",
        "Go ahead",
        "What's up?",
        "Tell me",
        "I'm here",
        "Ready when you are",
    ]

    async def _greet_and_listen(self):
        self._play_ding()
        greeting = random.choice(self._GREETINGS)
        if self.orb:
            self.orb.set_state(OrbState.WAKE.value)
        self._transition(AssistantState.SPEAKING)
        await self.tts.speak_streaming(greeting)
        self._enter_listening()

    async def _run_loop(self) -> None:
        self.state = AssistantState.IDLE
        self._last_activity = time.time()
        self._idle_since = time.time()
        self._transition(AssistantState.IDLE)

        last_health_check = time.time()

        while self._running:
            try:
                self.monitor.heartbeat()

                if time.time() - last_health_check > 30:
                    self._perform_self_healing()
                    last_health_check = time.time()

                await self._process_state()
                await asyncio.sleep(0.01)
            except Exception as e:
                logger.error(f"⚠️ Loop Error: {e}")
                self.monitor.log_crash(e)
                raise e

    def _perform_self_healing(self) -> None:
        self._sync_background_components()

        if self._wake_word_enabled and not self.audio.is_recording:
            logger.warning("🩹 Healing: Audio not recording. Restarting stream...")
            try:
                self._ensure_mic_active()
                self.bus.publish(
                    SubsystemStateEvent(
                        subsystem="mic",
                        state="healthy",
                        detail="audio stream restarted",
                    )
                )
            except Exception as e:
                logger.critical(
                    f"❌ Audio restart failed: {e}. Check microphone connection."
                )
                self.bus.publish(
                    SubsystemStateEvent(subsystem="mic", state="down", detail=str(e))
                )

        if self.wake_detector and not getattr(self.wake_detector, "_is_loaded", False):
            logger.warning(
                "🩹 Healing: Wake Word Detector not loaded. Retrying background load..."
            )
            self.bus.publish(
                SubsystemStateEvent(
                    subsystem="wake_word", state="degraded", detail="detector reloading"
                )
            )
            threading.Thread(target=self.wake_detector.load_model, daemon=True).start()

        if self.llm and hasattr(self.llm, "_last_provider"):
            if getattr(self.llm, "_all_providers_failed", False):
                logger.warning(
                    "⚠️ All LLM providers unavailable. Check API keys in .env or ensure Ollama is running."
                )
                self.bus.publish(
                    SubsystemStateEvent(
                        subsystem="llm",
                        state="down",
                        detail="all providers unavailable",
                    )
                )
            else:
                self.bus.publish(
                    SubsystemStateEvent(
                        subsystem="llm", state="healthy", detail="provider available"
                    )
                )

        if self._loop_thread and not self._loop_thread.is_alive():
            logger.critical("🩹 Critical: Async loop thread died!")

    async def _process_state(self) -> None:
        self._sync_background_components()

        if self.state == AssistantState.IDLE:
            if self._wake_triggered:
                self._wake_triggered = False
                self._in_session = True
                logger.info("   🎙️ Wake triggered — session started")
                await self._greet_and_listen()
                return

            idle_elapsed = time.time() - self._idle_since
            if (
                idle_elapsed > self._idle_hide_after
                and self.orb
                and not self._orb_is_hidden
            ):
                self.orb.set_state(OrbState.HIDDEN.value)
                self._orb_is_hidden = True
                logger.debug("   👁️ Orb hidden after idle timeout")

            if (
                not self._wake_word_enabled
                and self._mic_idle_release_after > 0
                and idle_elapsed > self._mic_idle_release_after
            ):
                self._release_microphone()

            while self._wake_word_enabled and self.audio.is_recording:
                chunk = self.audio.get_audio_chunk(timeout=0)
                if not chunk:
                    break
                if self.wake_detector:
                    detected = self.wake_detector.process_audio(chunk)
                    if detected:
                        await self._greet_and_listen()
                        return
                break

            if self.proactive_engine:
                suggestion = self.proactive_engine.check_triggers(
                    self._last_activity or time.time()
                )
                if suggestion:
                    logger.info(f"💡 Proactive Suggestion: {suggestion}")
                    self._play_ding()
                    self._transition(AssistantState.SPEAKING)
                    self.tts.stop()
                    await self.tts.speak_streaming(suggestion)
                    self._enter_idle()

        elif self.state == AssistantState.LISTENING:

            def on_audio_level(level: float):
                if self.orb:
                    self.orb.set_audio_level(level)

            if self._low_memory_mode and hasattr(self.stt, "reload_if_needed"):
                await asyncio.to_thread(self.stt.reload_if_needed)

            audio_bytes = await asyncio.to_thread(
                self.stt.listen_with_vad,
                self.audio,
                15.0,
                audio_level_callback=on_audio_level,
            )

            if self.orb:
                self.orb.set_audio_level(0.0)

            if audio_bytes:
                self._transition(AssistantState.PROCESSING)
                self._idle_since = time.time()
                await self._process_speech(audio_bytes)
            elif self._in_session and time.time() - self._last_activity < self._session_idle_timeout:
                pass
            else:
                self._in_session = False
                self._enter_idle()

        elif self.state == AssistantState.PROCESSING:
            pass

        elif self.state == AssistantState.SPEAKING:
            if time.time() - self._last_activity > self._ambient_timeout:
                self._transition(AssistantState.IDLE)

    def _play_ding(self) -> None:
        ding_path = SOUNDS_DIR / "ding.wav"
        if ding_path.exists():
            self.audio.play_file(str(ding_path))

    def _sync_background_components(self) -> None:
        handle = getattr(self, "component_handle", None)
        if handle is None:
            return
        self.wake_detector = handle.wake_detector
        self.task_executor = handle.task_executor

    async def _process_speech(self, audio_bytes: bytes) -> None:
        text, confidence = self.stt.transcribe(audio_bytes)
        logger.info(f"🗣️ User: {text} ({confidence:.2f})")

        if not text or confidence < MIN_COMMAND_CONFIDENCE:
            logger.info(
                "   🎤 Ignoring low-confidence transcript (%.2f < %.2f)",
                confidence,
                MIN_COMMAND_CONFIDENCE,
            )
            if not self._in_session:
                self._enter_idle()
            return

        final_text, should_continue = await self._handle_user_text(
            text,
            confidence=confidence,
            source="voice",
        )

        self._transition(AssistantState.SPEAKING)

        was_interrupted = threading.Event()
        interrupt_event = threading.Event()
        vad = InterruptionVAD(
            threshold=self._interrupt_threshold,
            required_ms=self._interrupt_ms,
        )

        def interruption_monitor():
            self._ensure_mic_active()
            while not interrupt_event.is_set():
                chunk = self.audio.get_audio_chunk(timeout=0.05)
                if chunk and vad.is_speech(chunk):
                    logger.info("   ⚠️ User interrupted speech!")
                    self._play_ding()
                    self.tts.stop()
                    was_interrupted.set()
                    break

        monitor_thread = threading.Thread(
            target=interruption_monitor, daemon=True
        )
        monitor_thread.start()

        try:
            await self.tts.speak_streaming(final_text)
        finally:
            interrupt_event.set()
            monitor_thread.join(timeout=0.2)

        if was_interrupted.is_set():
            logger.info("👂 User interrupted — listening...")
            threading.Thread(target=self.stt.reload_if_needed, daemon=True).start()
            self._enter_listening()
        elif self._in_session or (should_continue and self._followup_count < 1):
            self._followup_count += 1
            logger.info("👂 Session active — listening for next utterance...")
            threading.Thread(target=self.stt.reload_if_needed, daemon=True).start()
            self._ensure_mic_active()
            self._warm_stt_async()
            self._idle_since = time.time()
            self._orb_is_hidden = False
            if self.orb:
                self.orb.set_state(OrbState.IDLE.value)
            self._transition(AssistantState.LISTENING)
        else:
            self._in_session = False
            self._enter_idle()

    async def _handle_user_text(
        self, text: str, confidence: float = 1.0, source: str = "text"
    ) -> tuple[str, bool]:
        from assistant.skill_response import SkillResponse

        user_text = text.strip()
        if not user_text:
            raise ValueError("Text input cannot be empty")

        self.bus.publish(
            TranscriptionEvent(text=user_text, confidence=confidence, source=source)
        )
        routed_text = self._apply_aliases(user_text)

        response_text = await self.skill_router.route(
            routed_text,
            {"confidence": confidence, "source": source, "input_mode": "text"},
        )

        if not response_text:
            recent_history = self.memory.get_recent(10)
            response_text = await self.llm.chat(routed_text, recent_history)

        should_continue = False
        final_text = str(response_text)
        is_skill = False

        if isinstance(response_text, SkillResponse):
            final_text = response_text.text
            should_continue = response_text.continue_listening
            is_skill = True

        if not should_continue:
            should_continue = self._should_continue_listening(final_text)

        self.bus.publish(
            ResponseEvent(text=final_text, is_skill=is_skill, source=source)
        )
        self.memory.add_exchange(user_text, final_text)
        return final_text, should_continue

    async def process_text_chat(
        self, text: str, speak: bool = False, source: str = "dashboard"
    ) -> str:
        user_text = text.strip()
        if not user_text:
            raise ValueError("Text input cannot be empty")

        logger.info("💬 User (%s): %s", source, user_text)
        self._idle_since = time.time()
        self._orb_is_hidden = False
        self._transition(AssistantState.PROCESSING)

        final_text, _ = await self._handle_user_text(
            user_text, confidence=1.0, source=source
        )

        if speak:
            self._transition(AssistantState.SPEAKING)
            try:
                await self.tts.speak_streaming(final_text)
            finally:
                self._enter_idle()
        else:
            self._enter_idle()

        return final_text

    def submit_text_chat(
        self,
        text: str,
        timeout: float = 60.0,
        speak: bool = False,
        source: str = "dashboard",
    ) -> str:
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("Assistant loop is not running")

        future = asyncio.run_coroutine_threadsafe(
            self.process_text_chat(text, speak=speak, source=source),
            self._loop,
        )
        return future.result(timeout=timeout)

    def _should_continue_listening(self, text: str) -> bool:
        if text.endswith("?"):
            return True
        return any(p in text.lower() for p in self.FOLLOWUP_PHRASES)

    def clear_memory(self) -> None:
        self.memory.clear()
        self.long_term_memory.clear()
        logger.info("🗑️ Conversation and Long-Term memory cleared")

    def shutdown(self) -> None:
        logger.info("🛑 Shutting down...")
        self._running = False

        try:
            from skills.mcp_skill import MCPSkill

            if callable(getattr(MCPSkill, "cleanup_all", None)):
                if asyncio.iscoroutinefunction(MCPSkill.cleanup_all):
                    if self._loop and self._loop.is_running():
                        asyncio.run_coroutine_threadsafe(
                            MCPSkill.cleanup_all(), self._loop
                        ).result(timeout=3)
                    else:
                        asyncio.run(MCPSkill.cleanup_all())
                else:
                    MCPSkill.cleanup_all()
            logger.info("🔌 MCP Subprocesses stopped")
        except ImportError:
            pass
        except Exception as e:
            logger.warning(f"Failed to cleanup MCPSkill: {e}")

        self._cancel_stt_unload()
        if hasattr(self.stt, "unload_models"):
            try:
                self.stt.unload_models()
            except Exception:
                pass
        if hasattr(self, "audio"):
            self.audio.stop_recording()
            self.audio.stop_stream()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)


def main():
    args = parse_args()
    setup_logger()

    from assistant.conversation_memory import ConversationMemory
    from assistant.long_term_memory import LongTermMemory

    deps = setup_dependencies()
    memory = ConversationMemory()
    ltm = LongTermMemory()

    orb = OrbOverlay()
    orb.start()
    orb.set_state(OrbState.HIDDEN.value)

    assistant = VoiceAssistant(
        audio=deps["audio"],
        stt=deps["stt"],
        tts=deps["tts"],
        llm=deps["llm"],
        skill_router=deps["skill_router"],
        event_bus=deps["event_bus"],
    )
    assistant.memory = memory
    assistant.long_term_memory = ltm

    event_bus = deps["event_bus"]

    def _toggle_mic(assistant, orb):
        def _inner():
            assistant.set_wake_word_enabled(not assistant._wake_word_enabled)

        return _inner

    def _on_tool_confirmed(event_bus):
        def _inner(tool_name: str, outcome: str):
            event_bus.publish(
                ConfirmationEvent(tool_name=tool_name, action=outcome, dry_run="")
            )

        return _inner

    import dashboard.app as _dash_app

    dashboard_bridge = None
    try:
        dashboard_bridge = DashboardBridge(event_bus)
    except Exception as e:
        logger.warning(f"   ⚠️ Dashboard bridge failed: {e}")

    _dash_app.init(
        dashboard_bridge,
        wake_cb=lambda: assistant.trigger_wake() or orb.set_state("listening"),
        clear_memory_cb=assistant.clear_memory,
        toggle_mic_cb=_toggle_mic(assistant, orb),
        confirm_cb=_on_tool_confirmed(event_bus),
        chat_cb=lambda message, speak=False: assistant.submit_text_chat(
            message, speak=speak, source="dashboard"
        ),
    )

    start_dashboard(args.dashboard_host, args.dashboard_port)

    event_bus.subscribe(StateChangeEvent, lambda e: update_ui(e.new_state))
    event_bus.subscribe(
        TranscriptionEvent, lambda e: orb.add_message(e.text, is_user=True)
    )
    event_bus.subscribe(ResponseEvent, lambda e: orb.add_message(e.text, is_user=False))
    event_bus.subscribe(
        StatusEvent, lambda e: orb.add_message(f"⚙️ {e.text}", is_user=False)
    )

    llm = deps["llm"]
    llm.register_status_callback(lambda txt: event_bus.publish(StatusEvent(text=txt)))

    def update_ui(state_name: str) -> None:
        orb.set_state(state_name.lower())

    assistant.set_ui_callback(update_ui)
    assistant.orb = orb

    try:
        assistant.initialize()
    except Exception as e:
        logger.error(f"Init failed: {e}")
        orb.stop()
        return

    def on_show():
        loop = assistant._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(assistant.trigger_wake)
        else:
            assistant.trigger_wake()
        orb.set_state("listening")

    def on_exit():
        loop = assistant._loop
        if loop and loop.is_running():
            loop.call_soon_threadsafe(assistant.shutdown)
        else:
            assistant.shutdown()
        orb.stop()
        tray.stop()
        os._exit(0)

    def run_assistant():
        asyncio.run(assistant.run())

    assistant_thread = threading.Thread(target=run_assistant, daemon=True)
    assistant_thread.start()

    def inject_assistant():
        assistant._ready.wait(timeout=15)
        try:
            from assistant.api_server import set_assistant as set_api_assistant

            set_api_assistant(assistant)
            logger.info("   ✓ Assistant injected into API server")
        except Exception as e:
            logger.warning(f"Failed to inject assistant: {e}")

    inject_thread = threading.Thread(target=inject_assistant, daemon=True)
    inject_thread.start()

    # Start API server in background thread for AionUI MCP
    api_port = int(os.environ.get("BUDDY_API_PORT", "8765"))

    def run_api_server():
        try:
            import uvicorn

            from assistant.api_server import app as api_app

            uvicorn.run(
                api_app,
                host="127.0.0.1",
                port=api_port,
                log_level="warning",
                log_config=None,
            )
        except Exception as e:
            logger.warning(f"API server failed: {e}")

    api_thread = threading.Thread(target=run_api_server, daemon=True)
    api_thread.start()
    logger.info(f"   🌐 API server: http://localhost:{api_port}")

    tray = SystemTrayApp(on_exit=on_exit, on_show=on_show)

    logger.info("🚀 Buddy Desktop App Running (Orb Mode)!")
    logger.info("   Check System Tray. Press Ctrl+Space to talk.")

    try:
        tray.run()
    except KeyboardInterrupt:
        on_exit()
    except Exception as e:
        logger.critical(f"Tray crashed: {e}")
        on_exit()


if __name__ == "__main__":
    main()
