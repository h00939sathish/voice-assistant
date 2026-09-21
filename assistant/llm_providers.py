"""
LLM Providers - Provider classes and client management
"""

import asyncio
import json
import os
from typing import Any

import ollama
from google import genai
from groq import Groq
from openai import OpenAI

from config import (
    FREELLMAPI_API_KEY,
    FREELLMAPI_BASE_URL,
    FREELLMAPI_MODEL,
    GEMINI_MODEL,
    LMSTUDIO_HOST,
    LMSTUDIO_MODEL,
    NVIDIA_MODEL,
    OLLAMA_KEEP_ALIVE,
    OLLAMA_MODEL,
    OLLAMA_MODELS,
    OPENCODE_API_KEY,
    OPENCODE_BASE_URL,
    OPENCODE_MODEL,
    OPENROUTER_MODEL,
)


class OllamaProvider:
    """Ollama local LLM provider"""

    def __init__(self):
        self._available: bool | None = None
        self._model_name = OLLAMA_MODEL
        self._model_names = OLLAMA_MODELS or [OLLAMA_MODEL]
        self._keep_alive = OLLAMA_KEEP_ALIVE

    @property
    def available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            ollama.Client(timeout=3.0).list()
            self._available = True
        except Exception:
            self._available = False
        return self._available

    def mark_unavailable(self):
        self._available = False

    @property
    def model_name(self) -> str:
        return self._model_name

    @model_name.setter
    def model_name(self, value: str):
        self._model_name = value

    @property
    def model_names(self) -> list[str]:
        return self._model_names


class LMStudioProvider:
    """LM Studio local LLM provider"""

    def __init__(self):
        self._available: bool | None = None
        self._client: OpenAI | None = None

    @property
    def available(self) -> bool:
        if self._available is not None:
            return self._available
        try:
            import requests

            requests.get(f"{LMSTUDIO_HOST}/v1/models", timeout=1)
            self._available = True
            if not self._client:
                self._client = OpenAI(
                    base_url=f"{LMSTUDIO_HOST}/v1", api_key="lm-studio"
                )
        except Exception:
            self._available = False
        return self._available

    @property
    def client(self) -> OpenAI | None:
        if self._available and not self._client:
            self._client = OpenAI(base_url=f"{LMSTUDIO_HOST}/v1", api_key="lm-studio")
        return self._client

    def mark_unavailable(self):
        self._available = False


class GroqProvider:
    """Groq cloud LLM provider"""

    def __init__(self):
        self._client: Groq | None = None

    @property
    def client(self) -> Groq | None:
        if not self._client and os.getenv("GROQ_API_KEY"):
            self._client = Groq(api_key=os.getenv("GROQ_API_KEY"))
        return self._client


class NvidiaProvider:
    """Nvidia NIM cloud LLM provider"""

    def __init__(self):
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI | None:
        if not self._client and os.getenv("NVIDIA_API_KEY"):
            self._client = OpenAI(
                base_url="https://integrate.api.nvidia.com/v1",
                api_key=os.getenv("NVIDIA_API_KEY"),
            )
        return self._client


class GeminiProvider:
    """Gemini cloud LLM provider"""

    def __init__(self):
        self._client: genai.Client | None = None

    @property
    def client(self) -> genai.Client | None:
        if not self._client and os.getenv("GEMINI_API_KEY"):
            self._client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
        return self._client


class OpenRouterProvider:
    """OpenRouter cloud LLM provider"""

    def __init__(self):
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI | None:
        if not self._client and os.getenv("OPENROUTER_API_KEY"):
            self._client = OpenAI(
                base_url="https://openrouter.ai/api/v1",
                api_key=os.getenv("OPENROUTER_API_KEY"),
            )
        return self._client


class OpenCodeProvider:
    """OpenCode AI cloud LLM provider"""

    def __init__(self):
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI | None:
        if not self._client and OPENCODE_API_KEY:
            self._client = OpenAI(
                base_url=OPENCODE_BASE_URL,
                api_key=OPENCODE_API_KEY,
            )
        return self._client


class FreeLLMAPIProvider:
    """FreeLLMAPI proxy (OpenAI-compatible proxy)"""

    def __init__(self):
        self._client: OpenAI | None = None

    @property
    def client(self) -> OpenAI | None:
        if not self._client and FREELLMAPI_API_KEY:
            self._client = OpenAI(
                base_url=FREELLMAPI_BASE_URL,
                api_key=FREELLMAPI_API_KEY,
            )
        return self._client


class ProviderRegistry:
    """Registry for all LLM providers"""

    def __init__(self):
        self.ollama = OllamaProvider()
        self.lmstudio = LMStudioProvider()
        self.groq = GroqProvider()
        self.nvidia = NvidiaProvider()
        self.gemini = GeminiProvider()
        self.openrouter = OpenRouterProvider()
        self.opencode = OpenCodeProvider()
        self.freellmapi = FreeLLMAPIProvider()
        self._last_health_results: list[dict[str, Any]] = []

    def get_last_health_results(self) -> list[dict[str, Any]]:
        """Results of the most recent health check: [{provider, ok, model}]."""
        return [dict(r) for r in self._last_health_results]

    def get_all_providers(self) -> list[dict[str, Any]]:
        return [
            {
                "name": "Ollama",
                "provider": self.ollama,
                "local": True,
                "latency": "fast",
                "reasoning": "medium",
            },
            {
                "name": "LM Studio",
                "provider": self.lmstudio,
                "local": True,
                "latency": "fast",
                "reasoning": "medium",
            },
            {
                "name": "OpenCode",
                "provider": self.opencode,
                "local": False,
                "latency": "fast",
                "reasoning": "high",
            },
            {
                "name": "Groq",
                "provider": self.groq,
                "local": False,
                "latency": "fast",
                "reasoning": "medium",
            },
            {
                "name": "Nvidia",
                "provider": self.nvidia,
                "local": False,
                "latency": "balanced",
                "reasoning": "high",
            },
            {
                "name": "Gemini",
                "provider": self.gemini,
                "local": False,
                "latency": "balanced",
                "reasoning": "high",
            },
            {
                "name": "OpenRouter",
                "provider": self.openrouter,
                "local": False,
                "latency": "balanced",
                "reasoning": "high",
            },
            {
                "name": "FreeLLMAPI",
                "provider": self.freellmapi,
                "local": False,
                "latency": "fast",
                "reasoning": "high",
            },
        ]

    def run_health_checks(self, emit_status=None):
        print("   Running background API health checks...")
        results: list[dict[str, Any]] = [
            {
                "provider": "ollama",
                "ok": bool(self.ollama.available),
                "model": self.ollama.model_name,
            }
        ]

        groq_client = self.groq.client
        if groq_client:
            try:
                groq_client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                    timeout=3.0,
                )
                results.append(
                    {"provider": "groq", "ok": True, "model": "llama-3.1-8b-instant"}
                )
            except Exception as e:
                print(
                    f"   [!] Groq health check failed. Disabling. ({type(e).__name__})"
                )
                results.append(
                    {"provider": "groq", "ok": False, "model": "llama-3.1-8b-instant"}
                )
        else:
            results.append(
                {"provider": "groq", "ok": False, "model": "llama-3.1-8b-instant"}
            )

        gemini_client = self.gemini.client
        if gemini_client:
            try:
                gemini_client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents="ping",
                )
                results.append({"provider": "gemini", "ok": True, "model": GEMINI_MODEL})
            except Exception as e:
                print(
                    f"   [!] Gemini health check failed. Disabling. ({type(e).__name__})"
                )
                results.append(
                    {"provider": "gemini", "ok": False, "model": GEMINI_MODEL}
                )
        else:
            results.append({"provider": "gemini", "ok": False, "model": GEMINI_MODEL})

        nvidia_client = self.nvidia.client
        if nvidia_client:
            try:
                nvidia_client.chat.completions.create(
                    model=NVIDIA_MODEL,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                    timeout=3.0,
                )
                results.append({"provider": "nvidia", "ok": True, "model": NVIDIA_MODEL})
            except Exception as e:
                print(
                    f"   [!] Nvidia health check failed. Disabling. ({type(e).__name__})"
                )
                results.append(
                    {"provider": "nvidia", "ok": False, "model": NVIDIA_MODEL}
                )
        else:
            results.append({"provider": "nvidia", "ok": False, "model": NVIDIA_MODEL})

        openrouter_client = self.openrouter.client
        if openrouter_client:
            try:
                openrouter_client.chat.completions.create(
                    model=OPENROUTER_MODEL,
                    messages=[{"role": "user", "content": "ping"}],
                    max_tokens=1,
                    timeout=3.0,
                )
                results.append(
                    {"provider": "openrouter", "ok": True, "model": OPENROUTER_MODEL}
                )
            except Exception as e:
                print(
                    f"   [!] OpenRouter health check failed. Disabling. ({type(e).__name__})"
                )
                results.append(
                    {"provider": "openrouter", "ok": False, "model": OPENROUTER_MODEL}
                )
        else:
            results.append(
                {"provider": "openrouter", "ok": False, "model": OPENROUTER_MODEL}
            )

        self._last_health_results = results
        print("   Health checks completed.")

    async def with_timeout(
        self,
        coro,
        provider_name: str,
        has_tools: bool = False,
        chat_timeout: float = 12.0,
        tool_timeout: float = 40.0,
    ):
        limit = tool_timeout if has_tools else chat_timeout
        try:
            return await asyncio.wait_for(coro, timeout=limit)
        except TimeoutError:
            print(f"   ⏱ {provider_name} timed out after {limit}s — trying next")
            return None
        except Exception:
            return None


async def chat_ollama(
    provider: OllamaProvider,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    """Chat with Ollama provider"""
    last_error = None
    for model_name in provider.model_names:
        try:
            response = await _chat_ollama_with_model(
                provider,
                model_name,
                build_messages_fn,
                user_message,
                history,
                tools,
                tool_discovery_top_k,
                execute_tool_batch_fn,
                discover_tools_fn,
                initial_toolset_fn,
                merge_tool_schemas_fn,
                parse_tool_args_fn,
                normalize_model_tool_call_fn,
                compact_tool_fn,
                tool_name_from_schema_fn,
            )
            if response:
                provider.model_name = model_name
                return response
        except Exception as e:
            last_error = e
            print(f"   [!] Ollama model {model_name}: {e}")

    if last_error is not None:
        print(f"   [!] Ollama: {last_error}")
    provider.mark_unavailable()
    return None


async def _chat_ollama_with_model(
    provider: OllamaProvider,
    model_name: str,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    messages = build_messages_fn(user_message, history)
    all_tools = tools or []
    available_tools = initial_toolset_fn(all_tools) if initial_toolset_fn else all_tools

    for _ in range(5):
        response = await asyncio.to_thread(
            ollama.chat,
            model=model_name,
            messages=messages,
            tools=available_tools if available_tools else None,
            keep_alive=provider._keep_alive,
        )

        message = response["message"]

        if message.get("tool_calls"):
            print(f"   🔧 Ollama Tool Calls detected: {len(message['tool_calls'])}")
            messages.append(message)

            pending_tool_messages = []
            executable_calls = []
            last_batch_should_halt = False
            last_batch_halt_message = ""

            for tool in message["tool_calls"]:
                fn_name = tool["function"]["name"]
                args = (
                    parse_tool_args_fn(tool["function"].get("arguments"))
                    if parse_tool_args_fn
                    else tool["function"].get("arguments", {})
                )
                fn_name, args = (
                    normalize_model_tool_call_fn(fn_name, args, user_message)
                    if normalize_model_tool_call_fn
                    else (fn_name, args)
                )
                print(f"   🚀 Dispatching {fn_name}({args})")

                if fn_name == "search_tools":
                    query = str(args.get("query", user_message))
                    top_k = args.get("top_k", tool_discovery_top_k)
                    discovered = (
                        await discover_tools_fn(query, all_tools, top_k)
                        if discover_tools_fn
                        else []
                    )
                    available_tools = (
                        merge_tool_schemas_fn(available_tools, discovered)
                        if merge_tool_schemas_fn
                        else discovered
                    )
                    result = json.dumps(
                        {
                            "query": query,
                            "returned": len(discovered),
                            "tools": [compact_tool_fn(schema) for schema in discovered]
                            if compact_tool_fn
                            else discovered,
                        }
                    )
                    pending_tool_messages.append(
                        {"role": "tool", "content": str(result)}
                    )
                    continue

                allowed_schema_names = (
                    {tool_name_from_schema_fn(schema) for schema in available_tools}
                    if tool_name_from_schema_fn
                    else set()
                )
                if fn_name not in allowed_schema_names:
                    result = f"Error: Tool '{fn_name}' must be discovered via search_tools first."
                    pending_tool_messages.append(
                        {"role": "tool", "content": str(result)}
                    )
                else:
                    executable_calls.append({"name": fn_name, "args": args})
                    pending_tool_messages.append(None)

            if execute_tool_batch_fn and executable_calls:
                execution_results = await execute_tool_batch_fn(
                    executable_calls, user_message
                )
                execution_iter = iter(execution_results)
                for pending_message in pending_tool_messages:
                    if pending_message is None:
                        messages.append(
                            {"role": "tool", "content": str(next(execution_iter, ""))}
                        )
                    else:
                        messages.append(pending_message)
                last_batch_should_halt, last_batch_halt_message = _halt_signal_from(
                    execute_tool_batch_fn
                )

            if last_batch_should_halt:
                return last_batch_halt_message or "Action cancelled."
        else:
            return message.get("content", "")
    return "Action required too many steps."


async def chat_lmstudio(
    provider: LMStudioProvider,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    return await chat_openai_compatible(
        provider.client,
        LMSTUDIO_MODEL,
        build_messages_fn,
        user_message,
        history,
        "LM Studio",
        tools,
        tool_discovery_top_k,
        execute_tool_batch_fn,
        discover_tools_fn,
        initial_toolset_fn,
        merge_tool_schemas_fn,
        parse_tool_args_fn,
        normalize_model_tool_call_fn,
        compact_tool_fn,
        tool_name_from_schema_fn,
    )


async def chat_groq(
    provider: GroqProvider,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    if not provider.client:
        return None

    estimated_tool_tokens = (
        len(str(initial_toolset_fn(tools or []))) / 4 if tools else 0
    )
    if estimated_tool_tokens > 4500:
        print(
            f"   ℹ️ Skipping Groq (estimated tool payload ~{estimated_tool_tokens:.0f} tokens exceeds API limits)"
        )
        return None

    return await chat_openai_compatible(
        provider.client,
        "llama-3.1-8b-instant",
        build_messages_fn,
        user_message,
        history,
        "Groq",
        tools,
        tool_discovery_top_k,
        execute_tool_batch_fn,
        discover_tools_fn,
        initial_toolset_fn,
        merge_tool_schemas_fn,
        parse_tool_args_fn,
        normalize_model_tool_call_fn,
        compact_tool_fn,
        tool_name_from_schema_fn,
    )


async def chat_nvidia(
    provider: NvidiaProvider,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    return await chat_openai_compatible(
        provider.client,
        NVIDIA_MODEL,
        build_messages_fn,
        user_message,
        history,
        "Nvidia",
        tools,
        tool_discovery_top_k,
        execute_tool_batch_fn,
        discover_tools_fn,
        initial_toolset_fn,
        merge_tool_schemas_fn,
        parse_tool_args_fn,
        normalize_model_tool_call_fn,
        compact_tool_fn,
        tool_name_from_schema_fn,
    )


async def chat_openrouter(
    provider: OpenRouterProvider,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    return await chat_openai_compatible(
        provider.client,
        OPENROUTER_MODEL,
        build_messages_fn,
        user_message,
        history,
        "OpenRouter",
        tools,
        tool_discovery_top_k,
        execute_tool_batch_fn,
        discover_tools_fn,
        initial_toolset_fn,
        merge_tool_schemas_fn,
        parse_tool_args_fn,
        normalize_model_tool_call_fn,
        compact_tool_fn,
        tool_name_from_schema_fn,
    )


async def chat_opencode(
    provider: OpenCodeProvider,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    return await chat_openai_compatible(
        provider.client,
        OPENCODE_MODEL,
        build_messages_fn,
        user_message,
        history,
        "OpenCode",
        tools,
        tool_discovery_top_k,
        execute_tool_batch_fn,
        discover_tools_fn,
        initial_toolset_fn,
        merge_tool_schemas_fn,
        parse_tool_args_fn,
        normalize_model_tool_call_fn,
        compact_tool_fn,
        tool_name_from_schema_fn,
    )


def _halt_signal_from(execute_tool_batch_fn):
    """Read the router's post-batch halt flag from its bound execute method.

    ``execute_tool_batch_fn`` is always ``LLMRouter._execute_tool_batch``, so its
    ``__self__`` is the router that records ``_last_batch_should_halt`` when a
    tool returns a gated status (requires_confirmation / blocked / clarify).
    Providers extracted into free functions lost access to ``self``; this bridges
    the signal back so a denied confirmation stops the loop instead of retrying.
    """
    owner = getattr(execute_tool_batch_fn, "__self__", None)
    if owner is not None and getattr(owner, "_last_batch_should_halt", False):
        return True, getattr(owner, "_last_batch_halt_message", "")
    return False, ""


async def chat_freellmapi(
    provider: FreeLLMAPIProvider,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    return await chat_openai_compatible(
        provider.client,
        FREELLMAPI_MODEL,
        build_messages_fn,
        user_message,
        history,
        "FreeLLMAPI",
        tools,
        tool_discovery_top_k,
        execute_tool_batch_fn,
        discover_tools_fn,
        initial_toolset_fn,
        merge_tool_schemas_fn,
        parse_tool_args_fn,
        normalize_model_tool_call_fn,
        compact_tool_fn,
        tool_name_from_schema_fn,
    )


async def chat_openai_compatible(
    client,
    model: str,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
    provider_name: str,
    tools: list[dict] = None,
    tool_discovery_top_k: int = 3,
    execute_tool_batch_fn=None,
    discover_tools_fn=None,
    initial_toolset_fn=None,
    merge_tool_schemas_fn=None,
    parse_tool_args_fn=None,
    normalize_model_tool_call_fn=None,
    compact_tool_fn=None,
    tool_name_from_schema_fn=None,
) -> str | None:
    if not client:
        return None

    try:
        messages = build_messages_fn(user_message, history)
        all_tools = tools or []
        available_tools = (
            initial_toolset_fn(all_tools) if initial_toolset_fn else all_tools
        )
        last_batch_should_halt = False
        last_batch_halt_message = ""

        for _ in range(5):
            completion = await asyncio.to_thread(
                client.chat.completions.create,
                model=model,
                messages=messages,
                tools=available_tools if available_tools else None,
                temperature=0.7,
                max_tokens=1024,
                extra_headers={"HTTP-Referer": "https://github.com/buddy-assistant"}
                if provider_name == "OpenRouter"
                else None,
            )

            message = completion.choices[0].message

            if message.tool_calls:
                print(
                    f"   🔧 {provider_name} Tool Calls detected: {len(message.tool_calls)}"
                )

                tool_calls_dict = []
                for t in message.tool_calls:
                    tool_calls_dict.append(
                        {
                            "id": t.id,
                            "type": "function",
                            "function": {
                                "name": t.function.name,
                                "arguments": t.function.arguments,
                            },
                        }
                    )

                messages.append(
                    {
                        "role": "assistant",
                        "content": message.content or "",
                        "tool_calls": tool_calls_dict,
                    }
                )

                pending_tool_messages = []
                executable_calls = []

                for tool in message.tool_calls:
                    fn_name = tool.function.name
                    args = (
                        parse_tool_args_fn(tool.function.arguments)
                        if parse_tool_args_fn
                        else tool.function.arguments
                    )
                    fn_name, args = (
                        normalize_model_tool_call_fn(fn_name, args, user_message)
                        if normalize_model_tool_call_fn
                        else (fn_name, args)
                    )
                    print(f"   🚀 Dispatching {fn_name}({args})")

                    if fn_name == "search_tools":
                        query = str(args.get("query", user_message))
                        top_k = args.get("top_k", tool_discovery_top_k)
                        discovered = (
                            await discover_tools_fn(query, all_tools, top_k)
                            if discover_tools_fn
                            else []
                        )
                        available_tools = (
                            merge_tool_schemas_fn(available_tools, discovered)
                            if merge_tool_schemas_fn
                            else discovered
                        )
                        result = json.dumps(
                            {
                                "query": query,
                                "returned": len(discovered),
                                "tools": [
                                    compact_tool_fn(schema) for schema in discovered
                                ]
                                if compact_tool_fn
                                else discovered,
                            }
                        )
                        pending_tool_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool.id,
                                "name": fn_name,
                                "content": str(result),
                            }
                        )
                        continue

                    allowed_schema_names = (
                        {tool_name_from_schema_fn(schema) for schema in available_tools}
                        if tool_name_from_schema_fn
                        else set()
                    )
                    if fn_name not in allowed_schema_names:
                        result = f"Error: Tool '{fn_name}' must be discovered via search_tools first."
                        pending_tool_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool.id,
                                "name": fn_name,
                                "content": str(result),
                            }
                        )
                    else:
                        executable_calls.append({"name": fn_name, "args": args})
                        pending_tool_messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": tool.id,
                                "name": fn_name,
                                "content": None,
                            }
                        )

                if execute_tool_batch_fn and executable_calls:
                    execution_results = await execute_tool_batch_fn(
                        executable_calls, user_message
                    )
                    execution_iter = iter(execution_results)
                    for pending_message in pending_tool_messages:
                        if pending_message["content"] is None:
                            pending_message["content"] = str(next(execution_iter, ""))
                        messages.append(pending_message)
                    last_batch_should_halt, last_batch_halt_message = (
                        _halt_signal_from(execute_tool_batch_fn)
                    )

                if last_batch_should_halt:
                    return last_batch_halt_message or "Action cancelled."
            else:
                return message.content
        return "Task stopped after reaching maximum logical steps."
    except Exception as e:
        err_str = str(e)
        if "rate_limit_exceeded" in err_str or "413" in err_str or "429" in err_str:
            print(
                f"   ℹ️ {provider_name}: Rate limit or payload size exceeded. Skipping."
            )
        else:
            print(f"   [!] {provider_name}: {e}")
        return None


async def chat_gemini(
    provider: GeminiProvider,
    build_messages_fn,
    user_message: str,
    history: list[dict[str, str]],
) -> str | None:
    if not provider.client:
        return None
    try:
        messages = build_messages_fn(user_message, history)

        prompt_parts = []
        for msg in messages:
            role = (
                "Assistant" if msg["role"] == "assistant" else msg["role"].capitalize()
            )
            prompt_parts.append(f"{role}: {msg['content']}")

        full_prompt = "\n".join(prompt_parts) + "\nAssistant:"

        response = await asyncio.to_thread(
            provider.client.models.generate_content,
            model=GEMINI_MODEL,
            contents=full_prompt,
        )
        return response.text
    except Exception as e:
        print(f"   [!] Gemini: {e}")
        return None



async def stream_ollama(provider, messages, tools=None):
    if not provider.available:
        return

    model_name = getattr(provider, "model_name", None)
    if not model_name and hasattr(provider, "model_names") and provider.model_names:
        model_name = provider.model_names[0]

    # Provider is OllamaProvider, let's get the client. Normally it uses ollama module directly.
    import ollama
    client = ollama.Client(timeout=10.0)

    try:
        response_stream = await asyncio.to_thread(
            client.chat,
            model=model_name,
            messages=messages,
            stream=True,
            options={"temperature": 0.7}
        )

        for chunk in response_stream:
            if chunk.get("message", {}).get("content"):
                yield chunk["message"]["content"]
    except Exception as e:
        raise e

async def stream_gemini(provider, messages, tools=None):
    if not provider.client:
        return

    prompt = chr(10).join([m["content"] for m in messages])

    try:
        response_stream = await asyncio.to_thread(
            provider.client.models.generate_content,
            model=getattr(provider, "model", "gemini-1.5-pro"),
            contents=prompt,
            config=provider.client.types.GenerateContentConfig(
                temperature=0.7,
                system_instruction=messages[0]["content"] if messages and messages[0]["role"] == "system" else None
            ),
            stream=True
        )

        for chunk in response_stream:
            if chunk.text:
                yield chunk.text
    except Exception as e:
        raise e

async def stream_openai_compatible(client, model, messages, provider_name, tools=None):
    if not client:
        return

    try:
        completion = await asyncio.to_thread(
            client.chat.completions.create,
            model=model,
            messages=messages,
            temperature=0.7,
            max_tokens=1024,
            stream=True,
            extra_headers={"HTTP-Referer": "https://github.com/buddy-assistant"}
            if provider_name == "OpenRouter"
            else None,
        )

        for chunk in completion:
            if chunk.choices and chunk.choices[0].delta and chunk.choices[0].delta.content:
                yield chunk.choices[0].delta.content
    except Exception as e:
        raise e

async def stream_groq(provider, messages, tools=None):
    import os
    model = getattr(provider, "model", None) or os.getenv("GROQ_MODEL", "llama-3.1-8b-instant")
    gen = stream_openai_compatible(provider.client, model, messages, "Groq", tools)
    async for chunk in gen:
        yield chunk

async def stream_nvidia(provider, messages, tools=None):
    model = getattr(provider, "model", "meta/llama-3.1-8b-instruct")
    gen = stream_openai_compatible(provider.client, model, messages, "Nvidia", tools)
    async for chunk in gen:
        yield chunk

async def stream_openrouter(provider, messages, tools=None):
    model = getattr(provider, "model", "meta-llama/llama-3.1-8b-instruct:free")
    gen = stream_openai_compatible(provider.client, model, messages, "OpenRouter", tools)
    async for chunk in gen:
        yield chunk

async def stream_opencode(provider, messages, tools=None):
    model = getattr(provider, "model", "qwen-2.5-coder-32b")
    gen = stream_openai_compatible(provider.client, model, messages, "OpenCode", tools)
    async for chunk in gen:
        yield chunk

async def stream_freellmapi(provider, messages, tools=None):
    model = getattr(provider, "model", "gemini-1.5-pro")
    gen = stream_openai_compatible(provider.client, model, messages, "FreeLLMAPI", tools)
    async for chunk in gen:
        yield chunk

async def stream_lmstudio(provider, messages, tools=None):
    model = "local-model"
    gen = stream_openai_compatible(provider.client, model, messages, "LM Studio", tools)
    async for chunk in gen:
        yield chunk

