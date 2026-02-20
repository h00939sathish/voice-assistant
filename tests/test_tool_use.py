
import sys
import os
import asyncio
import pytest
from unittest.mock import MagicMock, patch

# Add project root to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

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
        "properties": {
             "city": {"type": "string"}
        },
        "required": ["city"]
    }
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
            {
                "function": {
                    "name": "mock_weather",
                    "arguments": {"city": "London"}
                }
            }
        ]
    }
    
    # 2. Final Response
    final_msg = {
        "role": "assistant",
        "content": "The weather in London is Sunny."
    }

    # Mock ollama.chat
    with patch('ollama.chat') as mock_chat:
        mock_chat.side_effect = [
            {"message": tool_call_msg}, # First call returns tool call
            {"message": final_msg}      # Second call returns final answer
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
        assert any(t["function"]["name"] == "mock_weather" for t in tools)

if __name__ == "__main__":
    asyncio.run(test_ollama_tool_execution())
    print("✅ test_ollama_tool_execution passed!")
