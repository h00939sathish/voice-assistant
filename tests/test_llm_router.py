import os
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from assistant.llm_router import LLMRouter


class TestLLMRouter:
    @pytest.fixture
    def router(self):
        with patch("assistant.llm_router.ProviderRegistry"):
            router = LLMRouter(prefer_local=True)
            router._provider_registry = MagicMock()
            router._fallback_config = MagicMock()
            router._fallback_chain = MagicMock()
            return router

    def test_router_initialization(self):
        with patch("assistant.llm_router.ProviderRegistry"):
            router = LLMRouter(prefer_local=True)
            assert router.prefer_local is True

    def test_router_initialization_no_local_preference(self):
        with patch("assistant.llm_router.ProviderRegistry"):
            router = LLMRouter(prefer_local=False)
            assert router.prefer_local is False

    def test_router_has_skip_memory_phrases(self, router):
        assert hasattr(router, "_SKIP_MEMORY_PHRASES")
        assert isinstance(router._SKIP_MEMORY_PHRASES, set)
        assert len(router._SKIP_MEMORY_PHRASES) > 0

    def test_router_has_no_tool_patterns(self, router):
        assert hasattr(router, "_NO_TOOL_PATTERNS")
        assert isinstance(router._NO_TOOL_PATTERNS, set)
        assert len(router._NO_TOOL_PATTERNS) > 0

    def test_router_has_action_verbs(self, router):
        assert hasattr(router, "_ACTION_VERBS")
        assert isinstance(router._ACTION_VERBS, set)
        assert len(router._ACTION_VERBS) > 0

    def test_register_status_callback(self, router):
        callback = MagicMock()
        router.register_status_callback(callback)
        assert router._status_callback == callback

    def test_set_task_executor(self, router):
        executor = MagicMock()
        router.set_task_executor(executor)
        assert router._task_executor == executor

    def test_get_tool_runner(self, router):
        tool_runner = router.get_tool_runner()
        assert tool_runner is not None


class TestLLMRouterDecisionMethods:
    @pytest.fixture
    def router(self):
        with patch("assistant.llm_router.ProviderRegistry"):
            router = LLMRouter(prefer_local=True)
            router._provider_registry = MagicMock()
            router._fallback_config = MagicMock()
            router._fallback_chain = MagicMock()
            return router

    @pytest.mark.asyncio
    async def test_decide_action_for_no_tool_pattern(self, router):
        result = await router._decide_action("hello")
        assert result == "answer_direct"

    @pytest.mark.asyncio
    async def test_decide_action_for_short_query_no_verbs(self, router):
        result = await router._decide_action("what time is it")
        assert result == "answer_direct"

    @pytest.mark.asyncio
    async def test_decide_action_for_action_verbs(self, router):
        result = await router._decide_action("search for weather")
        assert result == "single_tool"

    @pytest.mark.asyncio
    async def test_decide_action_for_compound_query(self, router):
        result = await router._decide_action("open notepad and then search")
        assert result == "multi_step"

    @pytest.mark.asyncio
    async def test_decide_action_for_multiple_verbs(self, router):
        result = await router._decide_action("search and delete files")
        assert result == "multi_step"

    @pytest.mark.asyncio
    async def test_classify_intent_uses_determine_intent(self, router):
        with patch("assistant.llm_router.determine_intent") as mock_determine:
            mock_determine.return_value = "complex"
            result = await router._classify_intent("explain how to create")
            assert result == "complex"
            mock_determine.assert_called_once()


class TestLLMRouterBuildMessages:
    @pytest.fixture
    def router(self):
        with patch("assistant.llm_router.ProviderRegistry"):
            router = LLMRouter(prefer_local=True)
            router._provider_registry = MagicMock()
            router._fallback_config = MagicMock()
            router._fallback_chain = MagicMock()
            return router

    def test_build_messages_basic(self, router):
        result = router._build_messages("Hello", [])
        assert isinstance(result, list)
        assert len(result) >= 1
        assert result[-1]["role"] == "user"
        assert result[-1]["content"] == "Hello"

    def test_build_messages_with_history(self, router):
        history = [
            {"role": "user", "content": "Previous message"},
            {"role": "assistant", "content": "Previous response"},
        ]
        result = router._build_messages("Hello", history)
        assert len(result) > 2
        assert result[-1]["role"] == "user"

    def test_should_skip_memory_for_time_query(self, router):
        assert router._should_skip_memory("what time is it") is True

    def test_should_skip_memory_for_date_query(self, router):
        assert router._should_skip_memory("what's the date today") is True

    def test_should_skip_memory_for_weather_query(self, router):
        assert router._should_skip_memory("weather") is True

    def test_should_not_skip_memory_for_regular_query(self, router):
        assert router._should_skip_memory("remind me to buy milk") is False


class TestLLMRouterToolSchemas:
    @pytest.fixture
    def router(self):
        with patch("assistant.llm_router.ProviderRegistry"):
            router = LLMRouter(prefer_local=True)
            router._provider_registry = MagicMock()
            router._fallback_chain = MagicMock()
            return router

    def test_tool_name_from_schema(self, router):
        schema = {"function": {"name": "test_tool"}}
        result = router._tool_name_from_schema(schema)
        assert result == "test_tool"

    def test_tool_name_from_schema_missing(self, router):
        schema = {}
        result = router._tool_name_from_schema(schema)
        assert result == ""

    def test_compact_tool(self, router):
        schema = {
            "function": {
                "name": "test_tool",
                "description": "Test description",
            }
        }
        result = router._compact_tool(schema)
        assert result["name"] == "test_tool"
        assert result["description"] == "Test description"

    def test_build_search_tools_schema(self, router):
        result = router._build_search_tools_schema()
        assert "type" in result
        assert result["type"] == "function"
        assert "function" in result
        assert result["function"]["name"] == "search_tools"

    def test_initial_toolset_without_dynamic_discovery(self, router):
        router._dynamic_tool_discovery = False
        tools = [{"function": {"name": "tool1"}}]
        result = router._initial_toolset(tools)
        assert result == tools

    def test_initial_toolset_with_dynamic_discovery(self, router):
        router._dynamic_tool_discovery = True
        tools = [{"function": {"name": "tool1"}}]
        result = router._initial_toolset(tools)
        assert len(result) == 1
        assert result[0]["function"]["name"] == "search_tools"

    def test_initial_toolset_empty(self, router):
        result = router._initial_toolset([])
        assert result == []

    def test_merge_tool_schemas(self, router):
        base = [{"function": {"name": "tool1"}}]
        extra = [{"function": {"name": "tool2"}}]
        result = router._merge_tool_schemas(base, extra)
        assert len(result) == 2

    def test_merge_tool_schemas_removes_duplicates(self, router):
        base = [{"function": {"name": "tool1"}}]
        extra = [{"function": {"name": "tool1"}}]
        result = router._merge_tool_schemas(base, extra)
        assert len(result) == 1

    def test_parse_tool_args_dict(self, router):
        args = {"query": "test"}
        result = router._parse_tool_args(args)
        assert result == args

    def test_parse_tool_args_json_string(self, router):
        args = '{"query": "test"}'
        result = router._parse_tool_args(args)
        assert result["query"] == "test"

    def test_parse_tool_args_plain_string(self, router):
        args = "plain text query"
        result = router._parse_tool_args(args)
        assert "query" in result


class TestLLMRouterToolDiscovery:
    @pytest.fixture
    def router(self):
        with patch("assistant.llm_router.ProviderRegistry"):
            router = LLMRouter(prefer_local=True)
            router._provider_registry = MagicMock()
            router._fallback_chain = MagicMock()
            return router

    def test_fallback_tool_discovery_with_matches(self, router):
        all_tools = [
            {"function": {"name": "search_tools", "description": "Search for tools"}},
            {"function": {"name": "weather", "description": "Get weather info"}},
        ]
        result = router._fallback_tool_discovery("weather forecast", all_tools, 3)
        assert len(result) >= 1

    def test_fallback_tool_discovery_empty_tools(self, router):
        result = router._fallback_tool_discovery("query", [], 3)
        assert result == []

    def test_fallback_tool_discovery_no_matches_returns_default(self, router):
        all_tools = [
            {"function": {"name": "tool1", "description": "description1"}},
            {"function": {"name": "tool2", "description": "description2"}},
        ]
        result = router._fallback_tool_discovery("xyz123", all_tools, 3)
        assert len(result) <= 3

    def test_normalize_model_tool_call_browser_search(self, router):
        fn_name = "browser"
        args = {"command": "search for python"}
        user_msg = "search for python"
        result = router._normalize_model_tool_call(fn_name, args, user_msg)
        assert result[0] == "browser_search"

    def test_normalize_model_tool_call_browser_navigate(self, router):
        fn_name = "browser"
        args = {"command": "open https://example.com"}
        user_msg = "open https://example.com"
        result = router._normalize_model_tool_call(fn_name, args, user_msg)
        assert result[0] == "browser_navigate"

    def test_normalize_model_tool_call_non_browser(self, router):
        fn_name = "other_tool"
        args = {}
        user_msg = ""
        result = router._normalize_model_tool_call(fn_name, args, user_msg)
        assert result[0] == "other_tool"


class TestLLMRouterExecuteToolBatch:
    @pytest.fixture
    def router(self):
        with patch("assistant.llm_router.ProviderRegistry"):
            router = LLMRouter(prefer_local=True)
            router._provider_registry = MagicMock()
            router._fallback_chain = MagicMock()
            router._tool_runner = MagicMock()
            router._tool_runner.execute = AsyncMock()
            return router

    @pytest.mark.asyncio
    async def test_execute_tool_batch_empty(self, router):
        result = await router._execute_tool_batch([], "test message")
        assert result == []

    @pytest.mark.asyncio
    async def test_execute_tool_batch_single_tool(self, router):
        tool_calls = [{"name": "test_tool", "args": {"arg1": "value1"}}]
        mock_result = MagicMock()
        mock_result.to_content_str = MagicMock(return_value="success")
        mock_result.status = "done"
        router._tool_runner.execute = AsyncMock(return_value=mock_result)

        result = await router._execute_tool_batch(tool_calls, "test message")
        assert len(result) == 1

