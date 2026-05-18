"""
Integration tests for the VoiceAssistant pipeline.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from assistant.events import EventBus, ResponseEvent, StateChangeEvent
from assistant.interfaces import IAudioManager, ILLMProvider, ISTTProvider, ITTSProvider
from assistant.skill_router import SkillRouter
from main import VoiceAssistant


def test_voice_assistant_creates_default_memory_when_not_injected():
    audio = MagicMock(spec=IAudioManager)
    stt = MagicMock(spec=ISTTProvider)
    tts = MagicMock(spec=ITTSProvider)
    llm = MagicMock(spec=ILLMProvider)
    skill_router = MagicMock(spec=SkillRouter)

    assistant = VoiceAssistant(
        audio=audio,
        stt=stt,
        tts=tts,
        llm=llm,
        skill_router=skill_router,
        event_bus=EventBus(persist=False),
    )

    assert assistant.memory is not None
    assert assistant.long_term_memory is not None


@pytest.mark.asyncio
async def test_assistant_speech_to_response_pipeline():
    """
    Verify the full pipeline:
    STT Transcribe -> Skill/LLM Process -> TTS Speak -> Event Emit
    """
    # 1. Setup Mocks manually to avoid Container resolution edge cases in tests
    audio = MagicMock(spec=IAudioManager)
    stt = MagicMock(spec=ISTTProvider)
    tts = MagicMock(spec=ITTSProvider)
    llm = MagicMock(spec=ILLMProvider)
    bus = EventBus()

    # Configure Mocks
    stt.transcribe.return_value = ("hello mock", 0.99)
    stt.load_models = MagicMock()

    # EXPLICIT ASYNC MOCKS
    llm.chat = AsyncMock(return_value="Mocked LLM Response")
    tts.speak_streaming = AsyncMock()
    tts.stop = MagicMock()

    # Mock SkillRouter
    skill_router = MagicMock(spec=SkillRouter)
    skill_router.route = AsyncMock(return_value=None)  # Force LLM fallback
    skill_router.load_skills = MagicMock()

    # 2. Initialize Assistant
    assistant = VoiceAssistant(
        audio=audio, stt=stt, tts=tts, llm=llm, skill_router=skill_router, event_bus=bus
    )

    # 3. Setup event tracking
    received_events = []
    bus.subscribe(StateChangeEvent, lambda e: received_events.append(e))
    bus.subscribe(ResponseEvent, lambda e: received_events.append(e))

    # 4. Act: Trigger speech processing
    audio_bytes = b"fake audio"
    await assistant._process_speech(audio_bytes)

    # Wait for async event handlers to finish
    await asyncio.sleep(0.1)

    # 5. Assert
    # Verify STT was called
    stt.transcribe.assert_called_once_with(audio_bytes)

    # Verify LLM was called (since SkillRouter returned None)
    llm.chat.assert_called_once()

    # Verify TTS was called with LLM response
    tts.speak_streaming.assert_called_once_with("Mocked LLM Response")

    # Verify Events
    assert any(
        isinstance(e, ResponseEvent) and e.text == "Mocked LLM Response"
        for e in received_events
    )
    assert any(
        isinstance(e, StateChangeEvent) and e.new_state == "SPEAKING"
        for e in received_events
    )
    assert any(
        isinstance(e, StateChangeEvent) and e.new_state == "IDLE"
        for e in received_events
    )
