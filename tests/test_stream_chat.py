import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from assistant.llm_router import LLMRouter

async def async_generator(items):
    for item in items:
        yield item
        await asyncio.sleep(0)

async def error_generator(items, error_after_items=0):
    for i in range(error_after_items):
        if i < len(items):
            yield items[i]
            await asyncio.sleep(0)
    raise ConnectionError("Simulated connection error")

@pytest.fixture
def base_router():
    with patch("assistant.llm_router.ProviderRegistry.run_health_checks"):
        router = LLMRouter(prefer_local=True)
        # Prevent any background health checks from firing
        return router

@pytest.mark.asyncio
async def test_stream_chat_yields_ordered_deltas(base_router):
    base_router._fallback_config.sort_providers = MagicMock(return_value=[
        ("Mock", MagicMock(), True)
    ])
    
    # We will mock the method that `stream_chat` uses internally, maybe `_stream_provider`
    base_router._stream_provider = AsyncMock(return_value=async_generator(["Hello", " ", "world"]))
    
    gen = base_router.stream_chat("hi", tools=None)
    chunks = [chunk async for chunk in gen]
    assert chunks == ["Hello", " ", "world"]

@pytest.mark.asyncio
async def test_stream_chat_fallback_before_first_token(base_router):
    # Provider 1 fails pre-token
    # Provider 2 succeeds
    base_router._fallback_config.sort_providers = MagicMock(return_value=[
        ("FailFirst", MagicMock(), True),
        ("SucceedSecond", MagicMock(), True)
    ])
    
    async def mock_stream_provider(name, *args, **kwargs):
        if name == "FailFirst":
            # Just raise right away
            raise ConnectionError("Pre-token error")
        else:
            return async_generator(["Got", " it"])
            
    base_router._stream_provider = AsyncMock(side_effect=mock_stream_provider)
    
    gen = base_router.stream_chat("hi", tools=None)
    chunks = [chunk async for chunk in gen]
    assert chunks == ["Got", " it"]

@pytest.mark.asyncio
async def test_stream_chat_error_after_first_token_propagates(base_router):
    base_router._fallback_config.sort_providers = MagicMock(return_value=[
        ("FailMidway", MagicMock(), True),
        ("Unreached", MagicMock(), True)
    ])
    
    # yields one item, then fails
    async def mock_stream_provider(name, *args, **kwargs):
        if name == "FailMidway":
            return error_generator(["Start ", " Middle"], error_after_items=1)
        return async_generator(["Unreached"])
        
    base_router._stream_provider = AsyncMock(side_effect=mock_stream_provider)
    
    gen = base_router.stream_chat("hi", tools=None)
    
    chunks = []
    with pytest.raises(ConnectionError):
        async for chunk in gen:
            chunks.append(chunk)
            
    assert chunks == ["Start "]

@pytest.mark.asyncio
async def test_stream_chat_non_streaming_provider_yields_one_chunk(base_router):
    base_router._fallback_config.sort_providers = MagicMock(return_value=[
        ("NoStream", MagicMock(), True)
    ])
    
    async def mock_stream_provider(name, *args, **kwargs):
        # Suppose this returns a string instead of an async generator, 
        # or we simulate how we handle non-streaming fallback
        return "This is the full response"
        
    base_router._stream_provider = AsyncMock(side_effect=mock_stream_provider)
    
    gen = base_router.stream_chat("hi", tools=None)
    chunks = [chunk async for chunk in gen]
    # Expected behavior from the prompt: non-streaming providers yield single chunk equal to full reply
    assert chunks == ["This is the full response"]


@pytest.mark.asyncio
async def test_stream_chat_real_async_generator_path(base_router):
    """Regression: exercise the *real* stream_chat -> _stream_provider ->
    _stream_gemini -> provider chain with a genuine async generator.

    The provider `stream_gemini` is an async generator (contains `yield`).
    The old code did `await stream_gemini(...)`, which raises TypeError and
    silently fell through to the error response. This test does NOT mock
    _stream_provider, so it catches that class of bug.
    """
    captured = {}

    async def fake_stream_gemini(provider, messages, tools=None):
        captured["messages"] = messages
        yield "Tick"
        yield " "
        yield "Tock"

    # Feed the real bound handler through the (mocked) sort step.
    base_router._fallback_config.sort_providers = MagicMock(return_value=[
        ("Gemini", base_router._stream_gemini, True)
    ])

    with patch("assistant.llm_providers.stream_gemini", new=fake_stream_gemini):
        gen = base_router.stream_chat("say hi")
        chunks = [chunk async for chunk in gen]

    assert chunks == ["Tick", " ", "Tock"]
    # stream_chat must build a proper message list (persona/system present),
    # not forward a raw string to the provider.
    assert isinstance(captured["messages"], list)
    assert captured["messages"][0]["role"] == "system"
    assert captured["messages"][-1] == {"role": "user", "content": "say hi"}
