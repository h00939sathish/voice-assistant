import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

import dashboard.app as dashboard_app
from assistant.events import EventBus, ResponseEvent
from assistant.interfaces import IAudioManager, ILLMProvider, ISTTProvider, ITTSProvider
from assistant.skill_router import SkillRouter
from main import VoiceAssistant
from tests.conftest import TEST_TOKEN, auth_headers


@pytest.mark.asyncio
async def test_text_chat_pipeline_uses_existing_skill_llm_flow():
    audio = MagicMock(spec=IAudioManager)
    stt = MagicMock(spec=ISTTProvider)
    tts = MagicMock(spec=ITTSProvider)
    llm = MagicMock(spec=ILLMProvider)
    bus = EventBus(persist=False)

    tts.speak_streaming = AsyncMock()
    skill_router = MagicMock(spec=SkillRouter)
    skill_router.route = AsyncMock(return_value=None)
    llm.chat = AsyncMock(return_value="Dashboard text response")

    # Mock memory to avoid AttributeError
    mock_memory = MagicMock()
    mock_memory.get_recent = MagicMock(return_value=[])

    assistant = VoiceAssistant(
        audio=audio,
        stt=stt,
        tts=tts,
        llm=llm,
        skill_router=skill_router,
        event_bus=bus,
    )
    assistant.memory = mock_memory

    responses = []
    bus.subscribe(ResponseEvent, lambda event: responses.append(event))

    reply = await assistant.process_text_chat(
        "hello from dashboard", speak=False, source="dashboard"
    )
    await asyncio.sleep(0.05)

    assert reply == "Dashboard text response"
    skill_router.route.assert_awaited_once()
    llm.chat.assert_awaited_once()
    tts.speak_streaming.assert_not_called()
    assert any(
        event.text == "Dashboard text response" and event.source == "dashboard"
        for event in responses
    )


def test_dashboard_chat_endpoint_returns_callback_response():
    client = dashboard_app.app.test_client()
    previous_callback = dashboard_app._chat_callback

    try:
        dashboard_app._chat_callback = lambda message, speak=False: (
            f"echo:{message}|speak={speak}"
        )

        response = client.post(
            "/api/chat",
            json={"message": "hello", "speak": True},
            headers=auth_headers(TEST_TOKEN),
        )

        assert response.status_code == 200
        assert response.get_json() == {
            "ok": True,
            "response": "echo:hello|speak=True",
        }
    finally:
        dashboard_app._chat_callback = previous_callback


def test_dashboard_chat_endpoint_rejects_empty_messages():
    client = dashboard_app.app.test_client()
    previous_callback = dashboard_app._chat_callback

    try:
        dashboard_app._chat_callback = lambda message, speak=False: "unused"

        response = client.post(
            "/api/chat", json={"message": "   "}, headers=auth_headers(TEST_TOKEN)
        )

        assert response.status_code == 400
        assert response.get_json()["ok"] is False
    finally:
        dashboard_app._chat_callback = previous_callback
