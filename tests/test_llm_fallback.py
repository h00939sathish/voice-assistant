import os
import sys
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Mock problematic dependencies before any imports
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

from assistant.llm_fallback import (
    FallbackChain,
    FallbackConfig,
    create_provider_priority_list,
    determine_intent,
)


class TestFallbackConfig:
    @pytest.fixture
    def config(self):
        return FallbackConfig(prefer_local=True)

    @pytest.fixture
    def config_no_local(self):
        return FallbackConfig(prefer_local=False)

    def test_fallback_config_initialization(self, config):
        assert config.prefer_local is True

    def test_fallback_config_initialization_no_local(self, config_no_local):
        assert config_no_local.prefer_local is False

    def test_compute_priority_fast_intent_prefers_local(self, config):
        provider_cfg = {
            "local": True,
            "latency_profile": "fast",
            "reasoning_strength": "medium",
        }
        priority = config.compute_priority(provider_cfg, "fast")
        assert priority[1] == 0

    def test_compute_priority_fast_intent_prefers_low_latency(self, config):
        provider_cfg = {
            "local": False,
            "latency_profile": "fast",
            "reasoning_strength": "medium",
        }
        priority = config.compute_priority(provider_cfg, "fast")
        assert priority[0] == 0

    def test_compute_priority_complex_intent_prefers_high_reasoning(self, config):
        provider_cfg = {
            "local": True,
            "latency_profile": "fast",
            "reasoning_strength": "high",
        }
        priority = config.compute_priority(provider_cfg, "complex")
        assert priority[0] == 0

    def test_compute_priority_defaults_to_balanced(self, config):
        provider_cfg = {}
        priority = config.compute_priority(provider_cfg, "fast")
        assert priority == (1, 1, 1)

    def test_sort_providers_returns_list_of_tuples(self, config):
        providers = [
            {
                "name": "Provider1",
                "handler": MagicMock(),
                "available": True,
                "latency_profile": "fast",
                "reasoning_strength": "medium",
                "local": True,
            },
            {
                "name": "Provider2",
                "handler": MagicMock(),
                "available": True,
                "latency_profile": "balanced",
                "reasoning_strength": "high",
                "local": False,
            },
        ]
        result = config.sort_providers(providers, "fast")
        assert isinstance(result, list)
        assert all(isinstance(item, tuple) for item in result)

    def test_sort_providers_respects_availability(self, config):
        providers = [
            {
                "name": "Provider1",
                "handler": MagicMock(),
                "available": True,
                "latency_profile": "fast",
                "reasoning_strength": "medium",
                "local": True,
            },
            {
                "name": "Provider2",
                "handler": MagicMock(),
                "available": False,
                "latency_profile": "fast",
                "reasoning_strength": "high",
                "local": False,
            },
        ]
        result = config.sort_providers(providers, "fast")
        assert result[0][2] is True
        assert result[1][2] is False


class TestFallbackChain:
    @pytest.fixture
    def config(self):
        return FallbackConfig(prefer_local=True)

    @pytest.fixture
    def chain(self, config):
        return FallbackChain(config)

    def test_fallback_chain_initialization(self, chain):
        assert chain._all_providers_failed is False
        assert chain.config is not None

    def test_mark_all_failed(self, chain):
        chain.mark_all_failed()
        assert chain._all_providers_failed is True

    def test_reset(self, chain):
        chain.mark_all_failed()
        chain.reset()
        assert chain._all_providers_failed is False

    def test_should_fallback_when_response_none(self, chain):
        assert chain.should_fallback(None) is True

    def test_should_not_fallback_when_response_exists(self, chain):
        assert chain.should_fallback("Some response") is False

    def test_get_error_response(self, chain):
        error_msg = chain.get_error_response()
        assert isinstance(error_msg, str)
        assert len(error_msg) > 0


class TestCreateProviderPriorityList:
    def test_create_provider_priority_list_returns_sorted_list(self):
        providers = [
            {
                "name": "Provider1",
                "handler": MagicMock(),
                "available": True,
                "latency_profile": "fast",
                "reasoning_strength": "medium",
                "local": True,
            },
            {
                "name": "Provider2",
                "handler": MagicMock(),
                "available": True,
                "latency_profile": "balanced",
                "reasoning_strength": "high",
                "local": False,
            },
        ]
        result = create_provider_priority_list(providers, "fast", prefer_local=True)
        assert isinstance(result, list)
        assert len(result) == 2

    def test_create_provider_priority_list_empty_input(self):
        result = create_provider_priority_list([], "fast", prefer_local=True)
        assert result == []


class TestDetermineIntent:
    def test_determine_intent_complex_for_multi_keyword_query(self):
        result = determine_intent("explain how to create and write")
        assert result == "complex"

    def test_determine_intent_complex_for_long_query(self):
        result = determine_intent(
            "this is a longer query with many words and more complexity"
        )
        assert result == "complex"

    def test_determine_intent_fast_for_short_simple_query(self):
        result = determine_intent("hello")
        assert result == "fast"

    def test_determine_intent_fast_for_single_word(self):
        result = determine_intent("time")
        assert result == "fast"

    @pytest.mark.parametrize(
        "query",
        [
            "search for weather",
            "find the answer",
            "open notepad",
            "run program",
            "create file",
            "delete item",
        ],
    )
    def test_determine_intent_with_action_verbs(self, query):
        result = determine_intent(query)
        assert result == "complex"


from unittest.mock import MagicMock
