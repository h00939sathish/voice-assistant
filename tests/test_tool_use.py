import asyncio
import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assistant.llm_router import LLMRouter
from assistant.skills_registry import skill
from skills.base_skill import BaseSkill


# Mock Skill
@skill(
    name="mock_weather",
    keywords=["weather"],
    description="Get weather",
    parameters={
        "type": "object",
        "properties": {"city": {"type": "string"}},
        "required": ["city"],
    },
)
class MockWeatherSkill(BaseSkill):
    async def handle(self, text, context):
        return f"Weather in {text} is Sunny"

    async def handle_tool_call(self, args, context):
        city = args.get("city", "Unknown")
        return f"Weather in {city} is Sunny"


@pytest.mark.asyncio
async def test_ollama_tool_execution():
    # Setup
    router = LLMRouter(prefer_local=True)
    router._ollama_available = True
    router._check_ollama = MagicMock(return_value=True)

    # Mock responses from Ollama
    # 1. Tool Call Response
    tool_call_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"function": {"name": "mock_weather", "arguments": {"city": "London"}}}
        ],
    }

    # 2. Final Response
    final_msg = {"role": "assistant", "content": "The weather in London is Sunny."}

    # Mock ollama.chat
    with patch("ollama.chat") as mock_chat:
        mock_chat.side_effect = [
            {"message": tool_call_msg},  # First call returns tool call
            {"message": final_msg},  # Second call returns final answer
        ]

        # Act
        response = await router.chat("What's the weather in London?")

        # Assert
        assert response == "The weather in London is Sunny."

        # Verify calls
        assert mock_chat.call_count == 2

        # Verify tool definitions were passed
        call_args = mock_chat.call_args_list[0]
        assert "tools" in call_args.kwargs
        tools = call_args.kwargs["tools"]
        tool_names = {t["function"]["name"] for t in tools}
        assert "mock_weather" in tool_names or "search_tools" in tool_names


@pytest.mark.asyncio
async def test_dynamic_search_tools_discovers_and_expands_tools():
    router = LLMRouter(prefer_local=True)
    router._ollama_available = True
    router._check_ollama = MagicMock(return_value=True)
    router._dynamic_tool_discovery = True

    discovered = [
        {
            "type": "function",
            "function": {
                "name": "mock_weather",
                "description": "Get weather",
                "parameters": {
                    "type": "object",
                    "properties": {"city": {"type": "string"}},
                    "required": ["city"],
                },
            },
        }
    ]
    router._discover_tools = AsyncMock(return_value=discovered)

    search_call_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "search_tools",
                    "arguments": {"query": "weather in london", "top_k": 3},
                }
            }
        ],
    }
    weather_call_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "function": {
                    "name": "mock_weather",
                    "arguments": {"city": "London"},
                }
            }
        ],
    }
    final_msg = {
        "role": "assistant",
        "content": "The weather in London is Sunny.",
    }

    with patch("ollama.chat") as mock_chat:
        mock_chat.side_effect = [
            {"message": search_call_msg},
            {"message": weather_call_msg},
            {"message": final_msg},
        ]

        response = await router.chat("What's the weather in London?")

        assert response == "The weather in London is Sunny."
        assert mock_chat.call_count == 3

        first_tools = mock_chat.call_args_list[0].kwargs["tools"]
        second_tools = mock_chat.call_args_list[1].kwargs["tools"]
        first_names = {t["function"]["name"] for t in first_tools}
        second_names = {t["function"]["name"] for t in second_tools}
        assert first_names == {"search_tools"}
        assert "mock_weather" in second_names


@pytest.mark.asyncio
async def test_ollama_falls_back_to_second_base_model():
    router = LLMRouter(prefer_local=True)
    router._ollama_available = True
    router._check_ollama = MagicMock(return_value=True)
    router._dynamic_tool_discovery = False
    router._ollama_model_names = ["phi4-mini:latest", "qwen3.5:4b-q4_K_M"]

    with patch("ollama.chat") as mock_chat:
        mock_chat.side_effect = [
            RuntimeError("first model failed"),
            {
                "message": {
                    "role": "assistant",
                    "content": "Recovered on fallback model.",
                }
            },
        ]

        response = await router.chat("Say hello")

        assert response == "Recovered on fallback model."
        assert mock_chat.call_count == 2
        assert mock_chat.call_args_list[0].kwargs["model"] == "phi4-mini:latest"
        assert mock_chat.call_args_list[1].kwargs["model"] == "qwen3.5:4b-q4_K_M"


@pytest.mark.asyncio
async def test_ollama_multi_tool_batch_uses_task_executor():
    router = LLMRouter(prefer_local=True)
    router._ollama_available = True
    router._check_ollama = MagicMock(return_value=True)
    router._dynamic_tool_discovery = False
    router._groq_client = None
    router._gemini_client = None
    router._nvidia_client = None
    router._openrouter_client = None
    router._lmstudio_available = False

    tool_call_msg = {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {"function": {"name": "mock_weather", "arguments": {"city": "London"}}},
            {"function": {"name": "mock_weather", "arguments": {"city": "Paris"}}},
        ],
    }
    final_msg = {
        "role": "assistant",
        "content": "London is Sunny and Paris is Sunny.",
    }

    with patch.object(
        router,
        "_execute_tool_batch",
        new=AsyncMock(
            return_value=["Weather in London is Sunny", "Weather in Paris is Sunny"]
        ),
    ) as mock_batch:
        with patch("ollama.chat") as mock_chat:
            mock_chat.side_effect = [
                {"message": tool_call_msg},
                {"message": final_msg},
            ]

            response = await router.chat("Compare weather in London and Paris")

            assert response == "London is Sunny and Paris is Sunny."
            mock_batch.assert_awaited_once()
            batch_calls = mock_batch.await_args.args[0]
            assert len(batch_calls) == 2
            assert batch_calls[0]["name"] == "mock_weather"
            assert batch_calls[1]["args"]["city"] == "Paris"


if __name__ == "__main__":
    asyncio.run(test_ollama_tool_execution())
    print("✅ test_ollama_tool_execution passed!")
