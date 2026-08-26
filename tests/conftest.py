"""
Shared Pytest fixtures and configurations.
Provides mocks for all core interfaces and DI setup.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from assistant.di import Container
from assistant.events import EventBus
from assistant.interfaces import IAudioManager, ILLMProvider, ISTTProvider, ITTSProvider
from assistant.skill_router import SkillRouter

# Hermetic default for the whole suite: token-protected HTTP endpoints accept
# this value without ever touching the real data/api_token file.
TEST_TOKEN = "test-token-123"


def auth_headers(token: str = TEST_TOKEN) -> dict[str, str]:
    """Auth header for requests against Buddy's token-protected servers."""
    return {"X-Buddy-Token": token}


@pytest.fixture(autouse=True)
def _buddy_api_token(monkeypatch):
    monkeypatch.setenv("BUDDY_API_TOKEN", TEST_TOKEN)


@pytest.fixture
def event_bus():
    """Returns a fresh EventBus for each test"""
    return EventBus()


@pytest.fixture
def di_container(event_bus):
    """
    Sets up a fresh DI Container with mock implementations.
    Explicitly uses AsyncMock for awaitable methods.
    """
    Container.clear()

    # 1. Create Mocks
    audio = MagicMock(spec=IAudioManager)
    audio.get_audio_chunk.return_value = b"\x00" * 1024
    audio.is_recording = True

    stt = MagicMock(spec=ISTTProvider)
    stt.transcribe.return_value = ("hello world", 0.95)
    stt.listen_with_vad.return_value = b"audio_bytes"
    stt.load_models = MagicMock()

    # ITTSProvider Mock
    tts = MagicMock(spec=ITTSProvider)
    tts.speak = AsyncMock()
    tts.speak_streaming = AsyncMock()
    tts.stop = MagicMock()

    # ILLMProvider Mock
    llm = MagicMock(spec=ILLMProvider)
    llm.chat = AsyncMock(return_value="This is a mock response.")

    # 2. Register instances (NOT types) to avoid re-instantiation
    Container.register(IAudioManager, audio)
    Container.register(ISTTProvider, stt)
    Container.register(ITTSProvider, tts)
    Container.register(ILLMProvider, llm)
    Container.register(EventBus, event_bus)

    # Register SkillRouter with the SAME mocks
    skill_router = SkillRouter(llm_router=llm, tts=tts)
    Container.register(SkillRouter, skill_router)

    yield Container
    Container.clear()
