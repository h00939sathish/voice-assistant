"""
LLM Router - Handles local (Ollama) and online (Groq, Nvidia, OpenRouter, Gemini) models

This is the main interface module. Provider implementations and fallback logic
have been extracted to separate modules:
- llm_providers.py: Provider classes and client management
- llm_fallback.py: Fallback logic and provider priority
"""

import asyncio
import json
import re
from collections.abc import Callable
from typing import Any

from assistant.fact_extractor import FactExtractor
from assistant.interfaces import ILLMProvider
from assistant.llm_fallback import FallbackChain, FallbackConfig, determine_intent
from assistant.llm_providers import (
    ProviderRegistry,
    chat_freellmapi,
    chat_gemini,
    chat_groq,
    chat_lmstudio,
    chat_nvidia,
    chat_ollama,
    chat_opencode,
    chat_openrouter,
)
from assistant.personality import SYSTEM_PROMPT
from assistant.task_executor import TaskState, TaskStep
from assistant.tool_runner import ToolRunner, ToolStatus
from config import (
    DYNAMIC_TOOL_DISCOVERY_ENABLED,
    DYNAMIC_TOOL_DISCOVERY_TOP_K,
    LLM_PRIORITY_MODE,
)


class LLMRouter(ILLMProvider):
    """Routes between multiple LLM providers with fallback logic"""

    _SKIP_MEMORY_PHRASES = {
        "time",
        "date",
        "weather",
        "play",
        "stop",
        "pause",
        "mute",
        "volume",
        "timer",
        "alarm",
        "lock",
        "sleep",
        "shutdown",
    }

    _NO_TOOL_PATTERNS = {
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank you",
        "bye",
        "goodbye",
        "good morning",
        "good night",
        "how are you",
        "who are you",
        "what's your name",
        "what is your name",
        "tell me a joke",
        "what can you do",
        "help",
    }

    _ACTION_VERBS = {
        "search",
        "find",
        "open",
        "run",
        "execute",
        "send",
        "create",
        "delete",
        "write",
        "play",
        "set",
        "remind",
        "schedule",
        "download",
        "install",
        "check",
        "scan",
        "launch",
        "close",
    }

    _CHAT_TIMEOUT = 12.0
    _TOOL_TIMEOUT = 40.0

    def __init__(
        self, conversation_memory=None, long_term_memory=None, prefer_local: bool = None
    ):
        # Use config LLM_PRIORITY_MODE to determine default
        if prefer_local is None:
            prefer_local = LLM_PRIORITY_MODE != "online_only"
        self.prefer_local = prefer_local
        self.conversation_memory = conversation_memory
        self.long_term_memory = long_term_memory

        self._provider_registry = ProviderRegistry()
        self._fallback_config = FallbackConfig(prefer_local)
        self._fallback_chain = FallbackChain(self._fallback_config)

        self._dynamic_tool_discovery = DYNAMIC_TOOL_DISCOVERY_ENABLED
        self._tool_discovery_top_k = max(1, DYNAMIC_TOOL_DISCOVERY_TOP_K)

        self.fact_extractor = (
            FactExtractor(
                self,
                conversation_memory=self.conversation_memory,
                long_term_memory=self.long_term_memory,
            )
            if self.long_term_memory
            else None
        )

        self._tool_runner = ToolRunner(status_callback=self._emit_status)
        self._task_executor = None
        self._last_batch_should_halt = False
        self._last_batch_halt_message = ""

        self._status_callback: Callable[[str], None] | None = None

        self._start_health_checks()

    def _start_health_checks(self):
        import threading

        threading.Thread(
            target=self._provider_registry.run_health_checks, daemon=True
        ).start()

    def get_provider_health(self) -> list[dict[str, Any]]:
        """Last provider health-check results: [{provider, ok, model}]."""
        return self._provider_registry.get_last_health_results()

    def register_status_callback(self, callback: Callable[[str], None]):
        self._status_callback = callback

    def set_task_executor(self, executor) -> None:
        self._task_executor = executor

    def get_tool_runner(self) -> ToolRunner:
        return self._tool_runner

    def _emit_status(self, status: str):
        if self._status_callback:
            try:
                self._status_callback(status)
            except Exception as e:
                print(f"Error in status callback: {e}")

    async def _execute_tool_batch(
        self,
        tool_calls: list[dict[str, Any]],
        user_message: str,
    ) -> list[str]:
        self._last_batch_should_halt = False
        self._last_batch_halt_message = ""
        if not tool_calls:
            return []

        if len(tool_calls) == 1 or self._task_executor is None:
            results = []
            for tool_call in tool_calls:
                tr = await self._tool_runner.execute(
                    tool_call["name"],
                    tool_call["args"],
                    user_intent=user_message,
                )
                results.append(tr.to_content_str())
                if tr.status in {
                    ToolStatus.REQUIRES_CONFIRMATION,
                    ToolStatus.BLOCKED,
                    ToolStatus.CLARIFICATION_NEEDED,
                }:
                    self._last_batch_should_halt = True
                    self._last_batch_halt_message = tr.to_content_str()
                    break
            return results

        task = self._task_executor.create_task(
            goal=user_message,
            steps=[
                TaskStep(
                    tool_name=tool_call["name"],
                    args=tool_call["args"],
                    description=f"Execute {tool_call['name']}",
                )
                for tool_call in tool_calls
            ],
        )
        task = await self._task_executor.run(task.id)

        results: list[str] = []
        for tool_call, step in zip(tool_calls, task.steps, strict=False):
            if step.status == "done":
                results.append(step.result or f"{tool_call['name']} completed.")
            elif step.result_status in {
                ToolStatus.REQUIRES_CONFIRMATION.value,
                ToolStatus.BLOCKED.value,
                ToolStatus.CLARIFICATION_NEEDED.value,
            }:
                halt_message = (
                    step.result
                    or step.error
                    or f"{tool_call['name']} did not complete."
                )
                self._last_batch_should_halt = True
                self._last_batch_halt_message = halt_message
                results.append(halt_message)
                break
            elif step.error:
                results.append(f"Error executing {tool_call['name']}: {step.error}")
            else:
                results.append(f"{tool_call['name']} did not complete.")
        return results

    def _emit_subsystem_health(
        self, subsystem: str, state: str, detail: str = ""
    ) -> None:
        try:
            from assistant.events import SubsystemStateEvent, bus

            bus.publish(
                SubsystemStateEvent(subsystem=subsystem, state=state, detail=detail)
            )
        except Exception:
            pass

    def _should_skip_memory(self, user_message: str) -> bool:
        lower = user_message.lower()
        return any(kw in lower for kw in self._SKIP_MEMORY_PHRASES)

    def _build_messages(
        self, user_message: str, history: list[dict[str, str]]
    ) -> list[dict[str, str]]:
        memory_prompt = ""

        if self.long_term_memory and not self._should_skip_memory(user_message):
            try:
                facts = self.long_term_memory.get_facts_for_prompt(query=user_message)
                if facts:
                    memory_prompt += "\n\nKNOWN FACTS:\n" + facts

                relationships = self.long_term_memory.get_relationship_context(
                    user_message
                )
                if relationships:
                    memory_prompt += "\n\nKNOWN RELATIONSHIPS:\n" + relationships
            except Exception:
                pass

        messages = [{"role": "system", "content": SYSTEM_PROMPT + memory_prompt}]

        if history:
            messages.extend(history)

        messages.append({"role": "user", "content": user_message})
        return messages

    @staticmethod
    def _tool_name_from_schema(schema: dict[str, Any]) -> str:
        return schema.get("function", {}).get("name", "")

    @staticmethod
    def _compact_tool(schema: dict[str, Any]) -> dict[str, str]:
        fn = schema.get("function", {})
        return {
            "name": fn.get("name", ""),
            "description": fn.get("description", ""),
        }

    def _build_search_tools_schema(self) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": "search_tools",
                "description": (
                    "Find the most relevant tools for the user's request. "
                    "Call this before using any other tool."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "Natural-language task to find tools for.",
                        },
                        "top_k": {
                            "type": "integer",
                            "description": "Maximum number of tools to return.",
                            "minimum": 1,
                            "maximum": 20,
                        },
                    },
                    "required": ["query"],
                },
            },
        }

    def _initial_toolset(self, all_tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not all_tools:
            return []
        if not self._dynamic_tool_discovery:
            return all_tools
        return [self._build_search_tools_schema()]

    @staticmethod
    def _merge_tool_schemas(
        base: list[dict[str, Any]], extra: list[dict[str, Any]]
    ) -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        seen: set[str] = set()
        for tool in (base or []) + (extra or []):
            name = tool.get("function", {}).get("name", "")
            if not name or name in seen:
                continue
            merged.append(tool)
            seen.add(name)
        return merged

    @staticmethod
    def _parse_tool_args(raw_args: Any) -> dict[str, Any]:
        if isinstance(raw_args, dict):
            return raw_args
        if isinstance(raw_args, str):
            text = raw_args.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {"query": text}
            except json.JSONDecodeError:
                return {"query": text}
        return {}

    def _fallback_tool_discovery(
        self, query: str, all_tools: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]]:
        tokens = set(re.findall(r"[a-z0-9]+", (query or "").lower()))
        scored = []
        for schema in all_tools:
            fn = schema.get("function", {})
            name = fn.get("name", "").lower()
            desc = (fn.get("description") or "").lower()
            haystack = f"{name} {desc}"
            score = sum(1 for token in tokens if token in haystack)
            if score > 0:
                scored.append((score, name, schema))

        scored.sort(key=lambda item: (-item[0], item[1]))
        if scored:
            return [item[2] for item in scored[:top_k]]

        return all_tools[: min(top_k, 3)]

    @staticmethod
    def _normalize_model_tool_call(
        fn_name: str, args: dict[str, Any], user_message: str
    ) -> tuple[str, dict[str, Any]]:
        normalized_name = fn_name
        normalized_args = dict(args or {})

        if fn_name != "browser":
            return normalized_name, normalized_args

        command = str(normalized_args.get("command") or user_message or "").strip()
        lower = command.lower()

        if "search for " in lower:
            query = command[lower.index("search for ") + len("search for ") :].strip(
                " ."
            )
            if query:
                return "browser_search", {"query": query}

        if lower.startswith("search "):
            query = command[len("search ") :].strip(" .")
            if query:
                return "browser_search", {"query": query}

        if lower.startswith("open "):
            target = command[len("open ") :].strip()
            if " and search for " in lower:
                query = command[
                    lower.index(" and search for ") + len(" and search for ") :
                ].strip(" .")
                if query:
                    return "browser_search", {"query": query}
            if target:
                if any(
                    token in target for token in (".", "http://", "https://", "www.")
                ):
                    return "browser_navigate", {"url": target}
                return "browser_search", {"query": target}

        return normalized_name, normalized_args

    async def _discover_tools(
        self, query: str, all_tools: list[dict[str, Any]], top_k: int
    ) -> list[dict[str, Any]]:
        if not all_tools:
            return []

        top_k = min(max(1, top_k), 20)
        name_to_schema = {
            self._tool_name_from_schema(schema): schema for schema in all_tools
        }

        try:
            from assistant.skills_registry import registry

            mcp_instance = registry.create_instance("mcp")
            if mcp_instance and hasattr(mcp_instance, "handle_tool_call"):
                router_result = await mcp_instance.handle_tool_call(
                    {
                        "_mcp_server": "router",
                        "_mcp_tool": "get_tools_for_query",
                        "query": query,
                        "top_k": top_k,
                    },
                    context={},
                )
                data = json.loads(router_result)
                names = [tool.get("name", "") for tool in data.get("tools", [])]
                discovered = [
                    name_to_schema[name] for name in names if name in name_to_schema
                ]
                if discovered:
                    print(
                        f"   🔍 search_tools: router returned {len(discovered)} tools"
                    )
                    return discovered[:top_k]
        except Exception as e:
            print(f"   [!] search_tools router fallback: {e}")

        discovered = self._fallback_tool_discovery(query, all_tools, top_k)
        print(f"   🔍 search_tools: lexical fallback returned {len(discovered)} tools")
        return discovered

    async def _get_all_tools_async(
        self, query: str = "", prefilter: bool = True
    ) -> list[dict]:
        from assistant.skills_registry import registry

        tools = registry.get_tool_definitions()

        try:
            mcp_instance = registry.create_instance("mcp")
            if mcp_instance and hasattr(mcp_instance, "get_mcp_tools"):
                mcp_tools = await asyncio.wait_for(
                    mcp_instance.get_mcp_tools(), timeout=5.0
                )
                if mcp_tools:
                    tools.extend(mcp_tools)
                    self._emit_subsystem_health(
                        "mcp", "healthy", f"{len(mcp_tools)} tools loaded"
                    )
                else:
                    self._emit_subsystem_health("mcp", "degraded", "no tools loaded")
        except TimeoutError:
            print("   [!] MCP dynamic tool discovery timed out after 5.0 seconds.")
            self._emit_subsystem_health("mcp", "degraded", "discovery timeout")
        except Exception as e:
            print(f"   [!] Failed to pull dynamic MCP tools: {e}")
            self._emit_subsystem_health("mcp", "degraded", str(e))

        if prefilter and query and tools:
            try:
                mcp_instance = registry.create_instance("mcp")
                if mcp_instance and hasattr(mcp_instance, "handle_tool_call"):
                    router_result = await mcp_instance.handle_tool_call(
                        {
                            "_mcp_server": "router",
                            "_mcp_tool": "get_tools_for_query",
                            "query": query,
                            "top_k": 12,
                        },
                        context={},
                    )
                    data = json.loads(router_result)
                    relevant_names = {t["name"] for t in data.get("tools", [])}
                    if relevant_names:
                        filtered = [
                            t
                            for t in tools
                            if t.get("function", {}).get("name", "") in relevant_names
                        ]
                        if filtered:
                            print(
                                f"   🔀 Router: {len(tools)} → {len(filtered)} tools for query"
                            )
                            return filtered
            except Exception as e:
                print(f"   [!] Tool Router unavailable, using full list: {e}")

        return tools

    async def _decide_action(self, text: str) -> str:
        lower = text.lower().strip()
        words = lower.split()

        if lower in self._NO_TOOL_PATTERNS:
            return "answer_direct"

        if len(words) <= 4 and not any(w in self._ACTION_VERBS for w in words):
            return "answer_direct"

        compound_markers = {"and then", "after that", "and also", "first do", "then do"}
        if any(m in lower for m in compound_markers):
            return "multi_step"

        action_count = sum(1 for w in words if w in self._ACTION_VERBS)
        if action_count >= 2:
            return "multi_step"

        try:
            from assistant.skills_registry import SkillsRegistry

            matched_skill = SkillsRegistry.match_skill(text)
            if matched_skill and getattr(matched_skill, "name", "") != "mcp":
                return "single_tool"
        except Exception:
            pass

        return "single_tool"

    async def _classify_intent(self, text: str) -> str:
        return determine_intent(text)

    async def _handle_task_control_message(self, user_message: str) -> str | None:
        if not self._task_executor:
            return None

        lower = user_message.lower().strip()
        if not lower:
            return None

        if (
            lower in {"task status", "status of task", "active task"}
            or "what are you working on" in lower
        ):
            return self._task_executor.get_task_summary()

        if lower in {"list tasks", "show tasks"}:
            tasks = sorted(
                self._task_executor.get_all_tasks(),
                key=lambda t: t.updated_at,
                reverse=True,
            )[:5]
            if not tasks:
                return "No tasks found."
            lines = ["Recent tasks:"]
            for task in tasks:
                lines.append(f"- {task.id} [{task.state.value}] {task.goal}")
            return "\n".join(lines)

        if lower.startswith("pause task") or lower in {
            "pause that",
            "pause it",
            "pause current task",
        }:
            task_id = None
            match = re.search(r"pause task\s+([a-z0-9-]+)$", lower)
            if match:
                task_id = match.group(1)

            target = (
                self._task_executor.get_task(task_id)
                if task_id
                else self._task_executor.get_active_task()
            )
            if not target or target.state != TaskState.RUNNING:
                return "No running task is available to pause."

            self._task_executor.pause(target.id)
            return f"Pause requested for task {target.id}."

        if lower.startswith("resume task") or lower in {
            "resume that",
            "resume it",
            "resume last task",
        }:
            task_id = None
            match = re.search(r"resume task\s+([a-z0-9-]+)$", lower)
            if match:
                task_id = match.group(1)

            target = (
                self._task_executor.get_task(task_id)
                if task_id
                else self._task_executor.get_latest_paused_task()
            )
            if not target:
                return "No paused task is available to resume."
            if target.state != TaskState.PAUSED:
                return f"Task {target.id} is not paused (state={target.state.value})."

            async def _resume_in_background(resume_task_id: str):
                try:
                    await self._task_executor.resume(resume_task_id)
                except Exception as e:
                    self._emit_status(f"Task {resume_task_id} resume failed: {e}")

            asyncio.create_task(_resume_in_background(target.id))
            return f"Resuming task {target.id} in the background."

        return None

    async def _call_provider(
        self, name: str, method, user_message: str, history, tools=None
    ):
        has_tools = bool(tools)
        if name == "Gemini":
            coro = method(
                self._provider_registry.gemini,
                self._build_messages,
                user_message,
                history,
            )
        else:
            coro = method(
                getattr(self._provider_registry, name.lower().replace(" ", "")),
                self._build_messages,
                user_message,
                history,
                tools,
                self._tool_discovery_top_k,
                self._execute_tool_batch,
                self._discover_tools,
                self._initial_toolset,
                self._merge_tool_schemas,
                self._parse_tool_args,
                self._normalize_model_tool_call,
                self._compact_tool,
                self._tool_name_from_schema,
            )
        return await self._provider_registry.with_timeout(
            coro, name, has_tools, self._CHAT_TIMEOUT, self._TOOL_TIMEOUT
        )

    async def chat(
        self, user_message: str, history: list[dict[str, str]] | None = None
    ) -> str:
        response = None
        self._fallback_chain.reset()

        task_control_response = await self._handle_task_control_message(user_message)
        if task_control_response is not None:
            return task_control_response

        action = await self._decide_action(user_message)
        print(f"   🎯 Decision: {action.upper()}")

        intent = await self._classify_intent(user_message)
        print(f"   🧠 Semantic Intent: {intent.upper()}")

        tools = []
        if action != "answer_direct":
            tools = await self._get_all_tools_async(
                query=user_message, prefilter=not self._dynamic_tool_discovery
            )

        providers = self._provider_registry.get_all_providers()
        base_providers = []
        for p in providers:
            pname = p["name"]
            if pname == "Ollama":
                available = p["provider"].available
                handler = self._chat_ollama
            elif pname == "LM Studio":
                available = p["provider"].available
                handler = self._chat_lmstudio
            elif pname == "Groq":
                available = p["provider"].client is not None
                handler = self._chat_groq
            elif pname == "Nvidia":
                available = p["provider"].client is not None
                handler = self._chat_nvidia
            elif pname == "Gemini":
                available = p["provider"].client is not None
                handler = self._chat_gemini
            elif pname == "OpenRouter":
                available = p["provider"].client is not None
                handler = self._chat_openrouter
            elif pname == "OpenCode":
                available = p["provider"].client is not None
                handler = self._chat_opencode
            elif pname == "FreeLLMAPI":
                available = p["provider"].client is not None
                handler = self._chat_freellmapi
            else:
                continue

            base_providers.append(
                {
                    "name": pname,
                    "handler": handler,
                    "available": available,
                    "latency_profile": p["latency"],
                    "reasoning_strength": p["reasoning"],
                    "local": p["local"],
                }
            )

        sorted_providers = self._fallback_config.sort_providers(base_providers, intent)

        for name, method, is_avail in sorted_providers:
            if not is_avail:
                continue

            response = await self._call_provider(
                name, method, user_message, history, tools if name != "Gemini" else None
            )

            if getattr(self, "_last_batch_should_halt", False):
                response = self._last_batch_halt_message
                break

            if response:
                break

        if response is None:
            self._fallback_chain.mark_all_failed()
            self._emit_subsystem_health("llm", "down", "All providers failed")
            return self._fallback_chain.get_error_response()

        if self.fact_extractor:
            try:
                asyncio.create_task(
                    self.fact_extractor.extract_facts_async(user_message, response)
                )
            except Exception as e:
                print(f"   [!] Fact Extraction Trigger Failed: {e}")

        return response

    async def _chat_ollama(
        self, provider, build_messages_fn, user_message, history, tools, *args, **kwargs
    ):
        return await chat_ollama(
            provider,
            build_messages_fn,
            user_message,
            history,
            tools,
            self._tool_discovery_top_k,
            self._execute_tool_batch,
            self._discover_tools,
            self._initial_toolset,
            self._merge_tool_schemas,
            self._parse_tool_args,
            self._normalize_model_tool_call,
            self._compact_tool,
            self._tool_name_from_schema,
        )

    async def _chat_lmstudio(
        self, provider, build_messages_fn, user_message, history, tools, *args, **kwargs
    ):
        return await chat_lmstudio(
            provider,
            build_messages_fn,
            user_message,
            history,
            tools,
            self._tool_discovery_top_k,
            self._execute_tool_batch,
            self._discover_tools,
            self._initial_toolset,
            self._merge_tool_schemas,
            self._parse_tool_args,
            self._normalize_model_tool_call,
            self._compact_tool,
            self._tool_name_from_schema,
        )

    async def _chat_groq(
        self, provider, build_messages_fn, user_message, history, tools, *args, **kwargs
    ):
        return await chat_groq(
            provider,
            build_messages_fn,
            user_message,
            history,
            tools,
            self._tool_discovery_top_k,
            self._execute_tool_batch,
            self._discover_tools,
            self._initial_toolset,
            self._merge_tool_schemas,
            self._parse_tool_args,
            self._normalize_model_tool_call,
            self._compact_tool,
            self._tool_name_from_schema,
        )

    async def _chat_nvidia(
        self, provider, build_messages_fn, user_message, history, tools, *args, **kwargs
    ):
        return await chat_nvidia(
            provider,
            build_messages_fn,
            user_message,
            history,
            tools,
            self._tool_discovery_top_k,
            self._execute_tool_batch,
            self._discover_tools,
            self._initial_toolset,
            self._merge_tool_schemas,
            self._parse_tool_args,
            self._normalize_model_tool_call,
            self._compact_tool,
            self._tool_name_from_schema,
        )

    async def _chat_openrouter(
        self, provider, build_messages_fn, user_message, history, tools, *args, **kwargs
    ):
        return await chat_openrouter(
            provider,
            build_messages_fn,
            user_message,
            history,
            tools,
            self._tool_discovery_top_k,
            self._execute_tool_batch,
            self._discover_tools,
            self._initial_toolset,
            self._merge_tool_schemas,
            self._parse_tool_args,
            self._normalize_model_tool_call,
            self._compact_tool,
            self._tool_name_from_schema,
        )

    async def _chat_opencode(
        self, provider, build_messages_fn, user_message, history, tools, *args, **kwargs
    ):
        return await chat_opencode(
            provider,
            build_messages_fn,
            user_message,
            history,
            tools,
            self._tool_discovery_top_k,
            self._execute_tool_batch,
            self._discover_tools,
            self._initial_toolset,
            self._merge_tool_schemas,
            self._parse_tool_args,
            self._normalize_model_tool_call,
            self._compact_tool,
            self._tool_name_from_schema,
        )

    async def _chat_freellmapi(
        self, provider, build_messages_fn, user_message, history, tools, *args, **kwargs
    ):
        return await chat_freellmapi(
            provider,
            build_messages_fn,
            user_message,
            history,
            tools,
            self._tool_discovery_top_k,
            self._execute_tool_batch,
            self._discover_tools,
            self._initial_toolset,
            self._merge_tool_schemas,
            self._parse_tool_args,
            self._normalize_model_tool_call,
            self._compact_tool,
            self._tool_name_from_schema,
        )

    async def _chat_gemini(
        self, provider, build_messages_fn, user_message, history, tools=None
    ):
        return await chat_gemini(provider, build_messages_fn, user_message, history)


    async def _stream_provider(self, name: str, method, messages: list[dict], tools=None):
        if name == "Gemini":
            return await method(self._provider_registry.gemini, messages, tools)
        else:
            provider_attr = name.lower().replace(" ", "")
            provider_instance = getattr(self._provider_registry, provider_attr)
            return await method(provider_instance, messages, tools)

    async def stream_chat(
        self, messages: list[dict], *, tools: list[dict] | None = None
    ):
        self._fallback_chain.reset()
        
        providers = self._provider_registry.get_all_providers()
        base_providers = []
        for p in providers:
            pname = p["name"]
            if pname == "Ollama":
                available = p["provider"].available
                handler = self._stream_ollama
            elif pname == "LM Studio":
                available = p["provider"].available
                handler = self._stream_lmstudio
            elif pname == "Groq":
                available = p["provider"].client is not None
                handler = self._stream_groq
            elif pname == "Nvidia":
                available = p["provider"].client is not None
                handler = self._stream_nvidia
            elif pname == "Gemini":
                available = p["provider"].client is not None
                handler = self._stream_gemini
            elif pname == "OpenRouter":
                available = p["provider"].client is not None
                handler = self._stream_openrouter
            elif pname == "OpenCode":
                available = p["provider"].client is not None
                handler = self._stream_opencode
            elif pname == "FreeLLMAPI":
                available = p["provider"].client is not None
                handler = self._stream_freellmapi
            else:
                continue

            base_providers.append(
                {
                    "name": pname,
                    "handler": handler,
                    "available": available,
                    "latency_profile": p["latency"],
                    "reasoning_strength": p["reasoning"],
                    "local": p["local"],
                }
            )

        # For stream_chat, we just use a general intent for sorting
        sorted_providers = self._fallback_config.sort_providers(base_providers, "general")
        
        for name, method, is_avail in sorted_providers:
            if not is_avail:
                continue
                
            streamed_at_least_one = False
            try:
                # call the stream method
                gen = await self._stream_provider(name, method, messages, tools)
                if isinstance(gen, str):
                    streamed_at_least_one = True
                    yield gen
                    return
                async for chunk in gen:
                    streamed_at_least_one = True
                    yield chunk
                return  # If we finished successfully, we are done
            except Exception as e:
                print(f"   [!] stream_chat failed for {name}: {e}")
                if streamed_at_least_one:
                    # propagated exception since we already yielded tokens
                    raise e
                    
        self._fallback_chain.mark_all_failed()
        self._emit_subsystem_health("llm", "down", "All stream providers failed")
        yield self._fallback_chain.get_error_response()

    async def _stream_ollama(self, provider, messages, tools):
        from assistant.llm_providers import stream_ollama
        return await stream_ollama(provider, messages, tools)

    async def _stream_lmstudio(self, provider, messages, tools):
        from assistant.llm_providers import stream_lmstudio
        return await stream_lmstudio(provider, messages, tools)

    async def _stream_groq(self, provider, messages, tools):
        from assistant.llm_providers import stream_groq
        return await stream_groq(provider, messages, tools)

    async def _stream_nvidia(self, provider, messages, tools):
        from assistant.llm_providers import stream_nvidia
        return await stream_nvidia(provider, messages, tools)

    async def _stream_openrouter(self, provider, messages, tools):
        from assistant.llm_providers import stream_openrouter
        return await stream_openrouter(provider, messages, tools)

    async def _stream_opencode(self, provider, messages, tools):
        from assistant.llm_providers import stream_opencode
        return await stream_opencode(provider, messages, tools)
        
    async def _stream_freellmapi(self, provider, messages, tools):
        from assistant.llm_providers import stream_freellmapi
        return await stream_freellmapi(provider, messages, tools)

    async def _stream_gemini(self, provider, messages, tools):
        from assistant.llm_providers import stream_gemini
        return await stream_gemini(provider, messages, tools)

    def get_memory_stats(self) -> dict[str, Any]:
        stats = {}
        if self.long_term_memory:
            ltm_stats = self.long_term_memory.get_stats()
            stats["long_term"] = ltm_stats
        return stats
