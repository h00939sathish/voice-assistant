import asyncio
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock problematic dependencies before any imports
import unittest.mock as stdlib_mock

stdlib_mock.MagicMock()
stdlib_mock.MagicMock()

# Create mock modules to bypass imports in assistant package
mock_modules = [
    "sounddevice",
    "faster_whisper",
    "torch",
    "whisper",
    "pyaudio",
    "cv2",
    "pytesseract",
    "screen_brightness_control",
    "psutil",
]
for mod_name in mock_modules:
    if mod_name not in sys.modules:
        sys.modules[mod_name] = MagicMock()

from assistant.llm_providers import (
    GeminiProvider,
    GroqProvider,
    LMStudioProvider,
    NvidiaProvider,
    OllamaProvider,
    OpenRouterProvider,
    ProviderRegistry,
)


class TestOllamaProvider:
    @pytest.fixture
    def provider(self):
        return OllamaProvider()

    def test_ollama_provider_initialization(self, provider):
        assert provider._model_name is not None
        assert provider._model_names is not None
        assert provider._keep_alive is not None

    def test_ollama_model_name_getter_setter(self, provider):
        assert provider.model_name is not None
        new_model = "llama3:70b"
        provider.model_name = new_model
        assert provider.model_name == new_model

    def test_ollama_model_names_getter(self, provider):
        assert isinstance(provider.model_names, list)

    @patch("assistant.llm_providers.ollama.Client")
    def test_ollama_available_when_list_succeeds(self, mock_client, provider):
        mock_client.return_value.list = MagicMock()
        provider._available = None
        assert provider.available is True
        mock_client.return_value.list.assert_called_once()

    @patch("assistant.llm_providers.ollama.Client")
    def test_ollama_unavailable_when_list_fails(self, mock_client, provider):
        mock_client.return_value.list = MagicMock(side_effect=Exception("Connection failed"))
        provider._available = None
        assert provider.available is False

    def test_ollama_mark_unavailable(self, provider):
        provider._available = True
        provider.mark_unavailable()
        assert provider._available is False


class TestLMStudioProvider:
    @pytest.fixture
    def provider(self):
        return LMStudioProvider()

    def test_lmstudio_provider_initialization(self, provider):
        assert provider._available is None
        assert provider._client is None

    @patch("requests.get")
    @patch("assistant.llm_providers.LMSTUDIO_HOST", "http://localhost:1234")
    def test_lmstudio_available_when_request_succeeds(self, mock_get, provider):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        provider._available = None
        assert provider.available is True

    @patch("requests.get")
    @patch("assistant.llm_providers.LMSTUDIO_HOST", "http://localhost:1234")
    def test_lmstudio_unavailable_when_request_fails(self, mock_get, provider):
        mock_get.side_effect = Exception("Connection refused")
        provider._available = None
        assert provider.available is False

    @patch("requests.get")
    @patch("assistant.llm_providers.LMSTUDIO_HOST", "http://localhost:1234")
    def test_lmstudio_client_created_on_demand(self, mock_get, provider):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        provider._available = True
        client = provider.client
        assert client is not None

    def test_lmstudio_mark_unavailable(self, provider):
        provider._available = True
        provider.mark_unavailable()
        assert provider._available is False


class TestGroqProvider:
    @pytest.fixture
    def provider(self):
        return GroqProvider()

    def test_groq_provider_initialization(self, provider):
        assert provider._client is None

    @patch.dict(os.environ, {"GROQ_API_KEY": "test-key"})
    @patch("assistant.llm_providers.Groq")
    def test_groq_client_created_when_api_key_present(self, mock_groq, provider):
        mock_client = MagicMock()
        mock_groq.return_value = mock_client
        client = provider.client
        assert client is not None
        mock_groq.assert_called_once_with(api_key="test-key")

    @patch.dict(os.environ, {}, clear=True)
    def test_groq_client_none_when_no_api_key(self, provider):
        client = provider.client
        assert client is None


class TestNvidiaProvider:
    @pytest.fixture
    def provider(self):
        return NvidiaProvider()

    def test_nvidia_provider_initialization(self, provider):
        assert provider._client is None

    @patch.dict(os.environ, {"NVIDIA_API_KEY": "test-key"})
    @patch("assistant.llm_providers.OpenAI")
    def test_nvidia_client_created_when_api_key_present(self, mock_openai, provider):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        client = provider.client
        assert client is not None
        mock_openai.assert_called_once()

    @patch.dict(os.environ, {}, clear=True)
    def test_nvidia_client_none_when_no_api_key(self, provider):
        client = provider.client
        assert client is None


class TestGeminiProvider:
    @pytest.fixture
    def provider(self):
        return GeminiProvider()

    def test_gemini_provider_initialization(self, provider):
        assert provider._client is None

    @patch.dict(os.environ, {"GEMINI_API_KEY": "test-key"})
    @patch("assistant.llm_providers.genai.Client")
    def test_gemini_client_created_when_api_key_present(
        self, mock_client_class, provider
    ):
        mock_client = MagicMock()
        mock_client_class.return_value = mock_client
        client = provider.client
        assert client is not None
        mock_client_class.assert_called_once_with(api_key="test-key")

    @patch.dict(os.environ, {}, clear=True)
    def test_gemini_client_none_when_no_api_key(self, provider):
        client = provider.client
        assert client is None


class TestOpenRouterProvider:
    @pytest.fixture
    def provider(self):
        return OpenRouterProvider()

    def test_openrouter_provider_initialization(self, provider):
        assert provider._client is None

    @patch.dict(os.environ, {"OPENROUTER_API_KEY": "test-key"})
    @patch("assistant.llm_providers.OpenAI")
    def test_openrouter_client_created_when_api_key_present(
        self, mock_openai, provider
    ):
        mock_client = MagicMock()
        mock_openai.return_value = mock_client
        client = provider.client
        assert client is not None

    @patch.dict(os.environ, {}, clear=True)
    def test_openrouter_client_none_when_no_api_key(self, provider):
        client = provider.client
        assert client is None


class TestProviderRegistry:
    @pytest.fixture
    def registry(self):
        return ProviderRegistry()

    def test_registry_contains_all_providers(self, registry):
        assert hasattr(registry, "ollama")
        assert hasattr(registry, "lmstudio")
        assert hasattr(registry, "groq")
        assert hasattr(registry, "nvidia")
        assert hasattr(registry, "gemini")
        assert hasattr(registry, "openrouter")

    def test_get_all_providers_returns_list(self, registry):
        providers = registry.get_all_providers()
        assert isinstance(providers, list)
        assert len(providers) > 0

    def test_get_all_providers_contains_expected_fields(self, registry):
        providers = registry.get_all_providers()
        for p in providers:
            assert "name" in p
            assert "provider" in p
            assert "local" in p
            assert "latency" in p
            assert "reasoning" in p

    def test_get_all_providers_includes_ollama(self, registry):
        providers = registry.get_all_providers()
        names = [p["name"] for p in providers]
        assert "Ollama" in names

    def test_get_all_providers_includes_groq(self, registry):
        providers = registry.get_all_providers()
        names = [p["name"] for p in providers]
        assert "Groq" in names

    def test_get_all_providers_local_providers_marked(self, registry):
        providers = registry.get_all_providers()
        local_providers = [p for p in providers if p.get("local")]
        assert len(local_providers) >= 2

    @pytest.mark.asyncio
    async def test_with_timeout_completes_within_limit(self, registry):
        async def slow_coro():
            await asyncio.sleep(0.1)
            return "success"

        result = await registry.with_timeout(slow_coro(), "TestProvider")
        assert result == "success"

    @pytest.mark.asyncio
    async def test_with_timeout_returns_none_on_timeout(self, registry):
        async def slow_coro():
            await asyncio.sleep(2.0)
            return "success"

        result = await registry.with_timeout(
            slow_coro(), "TestProvider", chat_timeout=0.1
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_with_timeout_returns_none_on_exception(self, registry):
        async def failing_coro():
            raise ValueError("Test error")

        result = await registry.with_timeout(failing_coro(), "TestProvider")
        assert result is None
