"""
Buddy Voice Assistant - Main Application (Desktop Mode)
Uses PyQt6 for Siri-like Orb Overlay and pystray for System Tray.
"""

import sys
import os
import time
import threading
import asyncio
from enum import Enum, auto
from pathlib import Path
from typing import Callable, Optional, List, Dict

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import ASSISTANT_NAME, SOUNDS_DIR
from assistant.logger import setup_logger, get_logger
from assistant.audio_manager import AudioManager
from assistant.wake_word import WakeWordDetector
from assistant.stt import SpeechToText
from assistant.tts import TextToSpeech
from assistant.llm_router import LLMRouter
from assistant.skill_response import SkillResponse
from assistant.skill_router import SkillRouter
from assistant.health_monitor import get_monitor
from assistant.conversation_memory import ConversationMemory
from assistant.long_term_memory import LongTermMemory
from assistant.orb_overlay import OrbOverlay, OrbState  # New Overlay
from gui.tray import SystemTrayApp
from assistant.di import container
from assistant.interfaces import IAudioManager, ISTTProvider, ITTSProvider, ILLMProvider
from assistant.events import EventBus, StateChangeEvent, TranscriptionEvent, ResponseEvent

logger = get_logger("main")


class AssistantState(Enum):
    """Voice assistant states"""
    IDLE = auto()
    LISTENING = auto()
    PROCESSING = auto()
    SPEAKING = auto()


class VoiceAssistant:
    """Main voice assistant application"""

    FOLLOWUP_PHRASES: List[str] = [
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

    COMMAND_ALIASES: Dict[str, str] = {
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

    def __init__(self, 
                 audio: IAudioManager, 
                 stt: ISTTProvider, 
                 tts: ITTSProvider, 
                 llm: ILLMProvider,
                 skill_router: SkillRouter,
                 event_bus: EventBus) -> None:
        self.state: AssistantState = AssistantState.IDLE
        self._running: bool = False
        self._wake_triggered: bool = False
        self._last_activity: float = time.time()
        self._ambient_timeout: float = 30.0  # Seconds before returning to idle
        self._keyboard_available: bool = False
        self.monitor = get_monitor()
        self.ui_callback: Optional[Callable] = None
        self.memory: ConversationMemory = ConversationMemory()
        self.long_term_memory: LongTermMemory = LongTermMemory()
        self.proactive_engine = None # Will init later
        self.wake_detector = None # Will be initialized in background

        # Dependencies
        self.audio = audio
        self.stt = stt
        self.tts = tts
        self.llm = llm
        self.skill_router = skill_router
        self.bus = event_bus

        self._loop: asyncio.AbstractEventLoop = asyncio.new_event_loop()
        self._loop_thread: Optional[threading.Thread] = None

        logger.info(f"  🤖 {ASSISTANT_NAME} Voice Assistant (Orb Mode)")

    def set_ui_callback(self, callback: Callable) -> None:
        self.ui_callback = callback

    def _apply_aliases(self, text: str) -> str:
        """Apply command aliases to input"""
        lower_text = text.lower().strip()
        for alias, command in self.COMMAND_ALIASES.items():
            if alias in lower_text:
                logger.debug(f"Applied alias: '{alias}' -> '{command}'")
                return command
        return text

    def _start_keyboard_listener(self) -> None:
        """Start keyboard listener for hotkeys"""
        try:
            import keyboard

            def on_hotkey():
                if not self._wake_triggered:
                    logger.info("   ⌨️ Hotkey triggered wake")
                    self._wake_triggered = True

            keyboard.add_hotkey("ctrl + space", on_hotkey, suppress=True)
            keyboard.add_hotkey("caps lock", on_hotkey, suppress=True)
            keyboard.add_hotkey("windows + s", on_hotkey, suppress=True)
            
            # UI Control Hotkeys
            def toggle_history():
                logger.info("   ⌨️ Hotkey: Toggle History")
                # Need a way to send 'toggle' to orb process
                # For now, just a placeholder or we extend the queue
                pass
            
            keyboard.add_hotkey("windows + h", toggle_history)
            
            self._keyboard_available = True
            logger.info("   ⌨️ Keyboard listener started (Ctrl+Space, CapsLock, Win+S, Win+H)")
        except ImportError:
            logger.warning("   ⌨️ keyboard package not installed. Hotkeys disabled.")
        except Exception as e:
            logger.warning(f"   ⌨️ Keyboard listener failed: {e}")

    def initialize(self) -> None:
        """Initialize all components (Async/Background where possible)"""
        logger.info("📦 Initializing system (Background Preloading Enabled)...")

        def run_loop():
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()

        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()

        # 1. Start audio immediately (lightweight)
        self.audio.start_stream()

        # 2. Start background preloading for heavy components
        def preload_heavy_components():
            logger.info("   🔄 Background: Starting sequential preloading...")
            
            # 1. STT (High Priority)
            try:
                logger.info("   🔄 Loading STT (1/3)...")
                self.stt.load_models()
                logger.info("   ✅ STT ready")
            except Exception as e:
                logger.error(f"   ❌ STT load failed: {e}")

            # 2. Wake Word (Wait for STT to finish)
            try:
                from assistant.wake_word import WakeWordDetector
                self.wake_detector = WakeWordDetector()
                
                logger.info("   🔄 Loading Wake Word (2/3)...")
                self.wake_detector.load_model()
                logger.info("   ✅ Wake Word ready")
            except Exception as e:
                logger.error(f"   ❌ Wake Word load failed: {e}")

            # 3. Skills (Wait for Wake Word)
            try:
                logger.info("   🔄 Loading Skills (3/3)...")
                self.skill_router.load_skills()
                logger.info("   ✅ Skills ready")
            except Exception as e:
                logger.error(f"   ❌ Skills load failed: {e}")
            
            logger.info("   🏁 Background: Preloading sequence finished")

        threading.Thread(target=preload_heavy_components, daemon=True).start()
        
        # 3. Load Proactive Engine (Internal logic, usually fast)
        try:
            from assistant.proactive_engine import ProactiveEngine
            self.proactive_engine = ProactiveEngine()
        except ImportError:
            logger.warning("⚠️ Proactive Engine could not be loaded")
        except Exception as e:
            logger.warning(f"⚠️ Proactive Error: {e}")

        logger.info("🚀 Buddy core initialized!")
        self.monitor.start()

        self._start_keyboard_listener()

    def _transition(self, new_state: AssistantState) -> None:
        """Transition state and notify via events and UI callback"""
        if self.state != new_state:
            old_state_name = self.state.name
            new_state_name = new_state.name
            
            logger.debug(f"[{old_state_name}] → [{new_state_name}]")
            
            # Emit Event
            self.bus.publish(StateChangeEvent(
                old_state=old_state_name,
                new_state=new_state_name
            ))
            
            self.state = new_state
            self._last_activity = time.time()
            
            if self.ui_callback:
                self.ui_callback(new_state_name)

    def trigger_wake(self) -> None:
        """External wake trigger (e.g. from Tray)"""
        self._wake_triggered = True

    async def run(self) -> None:
        """Watchdog wrapper for main loop"""
        self._running = True
        crash_count = 0
        last_crash_time = 0
        
        logger.info("🛡️ Watchdog active")
        
        while self._running:
            try:
                await self._run_loop()
            except asyncio.CancelledError:
                break
            except Exception as e:
                current_time = time.time()
                # Reset counter if last crash was > 60s ago
                if current_time - last_crash_time > 60:
                    crash_count = 0
                
                crash_count += 1
                last_crash_time = current_time
                
                logger.critical(f"🔥 Critical Failure ({crash_count}/3): {e}")
                
                # Emit Error Event
                from assistant.events import ErrorEvent
                self.bus.publish(ErrorEvent(error=e, component="VoiceAssistant"))
                
                if crash_count >= 3:
                    logger.critical("❌ Too many crashes. Aborting.")
                    self._running = False
                    break
                
                logger.info("🔄 Restarting in 2 seconds...")
                await asyncio.sleep(2)
        
        self.shutdown()

    async def _run_loop(self) -> None:
        """Main event loop logic with self-healing"""
        self.state = AssistantState.IDLE
        self._last_activity = time.time()
        self._transition(AssistantState.IDLE)
        
        last_health_check = time.time()
        
        while self._running:
            try:
                self.monitor.heartbeat()
                
                # Periodic health check (every 30s)
                if time.time() - last_health_check > 30:
                    self._perform_self_healing()
                    last_health_check = time.time()

                await self._process_state()
                await asyncio.sleep(0.01) # Yield control
            except Exception as e:
                logger.error(f"⚠️ Loop Error: {e}")
                self.monitor.log_crash(e)
                raise e

    def _perform_self_healing(self) -> None:
        """Check component health and restart if necessary"""
        # 1. Check Audio Stream
        if not self.audio.is_recording and self.state != AssistantState.IDLE:
             logger.warning("🩹 Healing: Audio recording stopped unexpectedly. Restarting...")
             self.audio.start_stream()
        
        # 2. Check Wake Word Detector
        if self.wake_detector and not self.wake_detector._is_loaded:
             logger.warning("🩹 Healing: Wake Word Detector not loaded. Retrying background load...")
             threading.Thread(target=self.wake_detector.load_model, daemon=True).start()

        # 3. Check loop thread
        if self._loop_thread and not self._loop_thread.is_alive():
             logger.critical("🩹 Critical: Async loop thread died! Attempting restart...")
             # Complex restart logic would go here
             pass

    async def _process_state(self) -> None:
        if self.state == AssistantState.IDLE:
            chunk = self.audio.get_audio_chunk()
            if chunk and self.wake_detector:
                # Wake detection is CPU heavy.
                detected = self.wake_detector.process_audio(chunk)
                if detected or self._wake_triggered:
                    self._wake_triggered = False
                    self._transition(AssistantState.LISTENING)
                else:
                    # check proactive triggers
                    if self.proactive_engine:
                        suggestion = self.proactive_engine.check_triggers(self._last_activity or time.time())
                        if suggestion:
                            logger.info(f"💡 Proactive Suggestion: {suggestion}")
                            self._play_ding()
                            self._transition(AssistantState.SPEAKING)
                            self.tts.stop() 
                            await self.tts.speak_streaming(suggestion)
                            self._transition(AssistantState.IDLE)

        elif self.state == AssistantState.LISTENING:
            # listen_with_vad IS blocking and takes time (up to 15s).
            # This MUST run in executor to avoid blocking the loop for others (like tray/hotkeys if shared loop?)
            # But here the loop IS this logic.
            # If we want hotkeys to interrupt, we need listen_with_vad to be interruptible or threaded.
            # For this refactor, we accept it blocks the loop state, but we should make it awaitable if possible.
            # Existing stt.listen_with_vad is likely synchronous.
            # We wrap it in to_thread for safety.
            
            audio_bytes = await asyncio.to_thread(self.stt.listen_with_vad, self.audio, 15.0)
            
            if audio_bytes:
                self._transition(AssistantState.PROCESSING)
                await self._process_speech(audio_bytes)
            else:
                self._transition(AssistantState.IDLE)

        elif self.state == AssistantState.PROCESSING:
            pass 

        elif self.state == AssistantState.SPEAKING:
            if time.time() - self._last_activity > self._ambient_timeout:
                self._transition(AssistantState.IDLE)

    def _play_ding(self) -> None:
        ding_path = SOUNDS_DIR / "ding.wav"
        if ding_path.exists():
            self.audio.play_file(str(ding_path))

    async def _process_speech(self, audio_bytes: bytes) -> None:
        text, confidence = self.stt.transcribe(audio_bytes)
        logger.info(f"🗣️ User: {text} ({confidence:.2f})")

        if not text or confidence < 0.4:
            self._transition(AssistantState.IDLE)
            return

        # Emit Transcription Event
        self.bus.publish(TranscriptionEvent(text=text, confidence=confidence))

        text = self._apply_aliases(text)

        # UI Update for processing text? Not supported by Orb directly (just state)
        
        response_text = await self.skill_router.route(text, {"confidence": confidence})

        if not response_text:
            # Main LLM Fallback (Memory already handled by VoiceAssistant logging below? 
            # Wait, LLMRouter uses history.
            recent_history = self.memory.get_recent(10)
            # chat is now async
            response_text = await self.llm.chat(text, recent_history)

        should_continue = False
        final_text = str(response_text)
        is_skill = False

        if isinstance(response_text, SkillResponse):
            final_text = response_text.text
            should_continue = response_text.continue_listening
            is_skill = True

        if not should_continue:
            should_continue = self._should_continue_listening(final_text)

        # Emit Response Event
        self.bus.publish(ResponseEvent(text=final_text, is_skill=is_skill))

        self.memory.add_exchange(text, final_text)

        self._transition(AssistantState.SPEAKING)
        await self.tts.speak_streaming(final_text)

        if should_continue:
            logger.info("👂 Listening for follow-up...")
            self._transition(AssistantState.LISTENING)
        else:
            self._transition(AssistantState.IDLE)

    def _should_continue_listening(self, text: str) -> bool:
        if text.endswith("?"):
            return True
        return any(p in text.lower() for p in self.FOLLOWUP_PHRASES)

    def clear_memory(self) -> None:
        """Clear conversation memory"""
        self.memory.clear()
        self.long_term_memory.clear()
        logger.info("🗑️ Conversation and Long-Term memory cleared")

    def shutdown(self) -> None:
        logger.info("🛑 Shutting down...")
        self._running = False
        if hasattr(self, "audio"):
            self.audio.stop_recording()
            self.audio.stop_stream()
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)


def main():
    """Desktop App Entry Point (PyQt6 + Pystray)"""
    setup_logger()

    # 0. Register Dependencies in Container
    container.register(IAudioManager, AudioManager)
    container.register(ISTTProvider, SpeechToText)
    container.register(ITTSProvider, TextToSpeech)
    
    # Initialize Memory
    memory = ConversationMemory()
    ltm = LongTermMemory()
    
    # Special handling for LLM which needs memory systems
    llm = LLMRouter(conversation_memory=memory, long_term_memory=ltm)
    container.register(ILLMProvider, llm)
    
    # Register SkillRouter with injected dependencies
    skill_router = SkillRouter(llm_router=llm, tts=container.resolve(ITTSProvider))
    container.register(SkillRouter, skill_router)

    # 1. Initialize Orb Overlay (Separate Process)
    orb = OrbOverlay()
    orb.start()
    orb.set_state(OrbState.IDLE.value) # Show immediately

    # 2. Initialize Assistant via DI
    assistant = VoiceAssistant(
        audio=container.resolve(IAudioManager),
        stt=container.resolve(ISTTProvider),
        tts=container.resolve(ITTSProvider),
        llm=container.resolve(ILLMProvider),
        skill_router=container.resolve(SkillRouter),
        event_bus=container.resolve(EventBus)
    )

    # 3. Connect UI to Event Bus
    event_bus = container.resolve(EventBus)
    event_bus.subscribe(StateChangeEvent, lambda e: update_ui(e.new_state))
    event_bus.subscribe(TranscriptionEvent, lambda e: orb.add_message(e.text, is_user=True))
    event_bus.subscribe(ResponseEvent, lambda e: orb.add_message(e.text, is_user=False))

    # Callback to update Orb
    def update_ui(state_name: str) -> None:
        # Map AssistantState names to OrbState values (all lowercase)
        # IDLE -> "idle", LISTENING -> "listening", etc.
        orb.set_state(state_name.lower())

    assistant.set_ui_callback(update_ui)

    try:
        assistant.initialize()
    except Exception as e:
        logger.error(f"Init failed: {e}")
        orb.stop()
        return

    # 3. Define Tray Callbacks
    def on_show():
        assistant.trigger_wake()
        orb.set_state("listening") # Feedback

    def on_exit():
        assistant.shutdown()
        orb.stop()
        tray.stop()
        os._exit(0) # Force exit threads

    # 4. Start Assistant Thread (Async Loop)
    def run_assistant():
        asyncio.run(assistant.run())

    assistant_thread = threading.Thread(target=run_assistant, daemon=True)
    assistant_thread.start()

    # 5. Run Tray (Blocking Main Thread) - Critical for stability
    tray = SystemTrayApp(on_exit=on_exit, on_show=on_show)
    
    logger.info("🚀 Buddy Desktop App Running (Orb Mode)!")
    logger.info("   Check System Tray. Press Ctrl+Space to talk.")
    
    try:
        tray.run() # This BLOCKS until tray.stop() is called
    except KeyboardInterrupt:
        on_exit()
    except Exception as e:
        logger.critical(f"Tray crashed: {e}")
        on_exit()

if __name__ == "__main__":
    main()
