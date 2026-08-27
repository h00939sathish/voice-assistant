import json
import pytest
from typing import AsyncIterator
from tests.conftest import auth_headers

TOKEN = "test-token-123"

@pytest.fixture(autouse=True)
def _token_env(monkeypatch):
    monkeypatch.setenv("BUDDY_API_TOKEN", TOKEN)

def test_chat_stream_success(monkeypatch):
    from fastapi.testclient import TestClient
    from assistant import api_server
    from assistant.api_server import app

    class DummyLLM:
        async def stream_chat(self, message, tools=None) -> AsyncIterator[str]:
            yield "Hello"
            yield " "
            yield "world"

    class DummyAssistant:
        def __init__(self):
            self.llm = DummyLLM()
            
    def fake_get_assistant():
        return DummyAssistant()

    monkeypatch.setattr(api_server, "_get_assistant", fake_get_assistant)
    monkeypatch.setattr(api_server, "set_state", lambda s: None)

    with TestClient(app) as client:
        response = client.post(
            "/api/chat/stream",
            json={"message": "hi"},
            headers=auth_headers(TOKEN)
        )
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")

        text = response.text
        lines = [line for line in text.splitlines() if line.strip()]

        assert len(lines) == 4
        assert lines[0] == 'data: {"delta": "Hello"}'
        assert lines[1] == 'data: {"delta": " "}'
        assert lines[2] == 'data: {"delta": "world"}'
        assert lines[3] == "data: [DONE]"

def test_chat_stream_error(monkeypatch):
    from fastapi.testclient import TestClient
    from assistant import api_server
    from assistant.api_server import app

    class DummyLLMError:
        async def stream_chat(self, message, tools=None) -> AsyncIterator[str]:
            yield "Hello"
            raise RuntimeError("Boom!")

    class DummyAssistantError:
        def __init__(self):
            self.llm = DummyLLMError()
            
    def fake_get_assistant():
        return DummyAssistantError()

    monkeypatch.setattr(api_server, "_get_assistant", fake_get_assistant)
    monkeypatch.setattr(api_server, "set_state", lambda s: None)

    with TestClient(app) as client:
        response = client.post(
            "/api/chat/stream",
            json={"message": "hi"},
            headers=auth_headers(TOKEN)
        )
        assert response.status_code == 200
        text = response.text
        lines = [line for line in text.splitlines() if line.strip()]

        assert len(lines) == 3
        assert lines[0] == 'data: {"delta": "Hello"}'
        assert lines[1] == 'data: {"error": "Boom!"}'
        assert lines[2] == "data: [DONE]"
