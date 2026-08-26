"""
Skill Router - Routes commands to skills using the registry.
Hybrid approach: keyword matching first, then LLM classification.
"""

from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import logging
from pathlib import Path
from typing import Any

try:
    import asyncio as _asyncio

    import ollama
except ImportError:
    ollama = None

from assistant.interfaces import ILLMProvider, ITTSProvider
from assistant.mcp_subprocess_loader import MCPSubprocessLoader, MCPSubprocessProxy
from assistant.skill_response import SkillResponse
from assistant.skills_registry import SkillsRegistry

logger = logging.getLogger("buddy.skill_router")

# Thread pool for parallel skill imports
_import_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="skill_import")


class SkillRouter:
    """
    Routes user input to appropriate skills.
    1. Fast keyword matching via registry (~1ms)
    2. LLM classification for ambiguous queries (~150ms)
    """

    _DIRECT_ROUTE_SKILLS = {
        "browser",
        "calendar",
        "clipboard",
        "computer_use",
        "file_manager",
        "google_search",
        "memory_control",
        "news",
        "registry",
        "reminder",
        "system_monitor",
        "time",
        "weather",
        "web",
    }

    def __init__(
        self,
        llm_router: ILLMProvider = None,
        tts: ITTSProvider = None,
        skills_dir: str = None,
        tool_runner: Any = None,
    ):
        self.llm = llm_router
        self.tts = tts
        self.tool_runner = tool_runner or (
            llm_router.get_tool_runner()
            if llm_router is not None and hasattr(llm_router, "get_tool_runner")
            else None
        )
        self._classifier_model = "gemma:2b"  # Fast, small model for classification
        self._instances = OrderedDict()  # LRU Cache for skill instances
        self._max_active_skills = 5

    def load_skills(self):
        """Load all registered skills from the registry."""
        logger.info("📦 Loading skills...")

        # Import all skill modules to trigger registration
        self._import_all_skills()

        # Log discovered skills (but don't instantiate yet)
        skills = SkillsRegistry.get_all_skills()
        logger.info(f"   Note: {len(skills)} skills registered (Lazy Loading Enabled)")
        for name, meta in skills.items():
            print(f"   - {name}: {meta.description[:50]}...")

    def _import_all_skills(self):
        """Import all skill modules to trigger @skill decorators."""
        skills_dir = Path(__file__).parent.parent / "skills"
        if not skills_dir.exists():
            return

        # Add skills dir to path for relative imports
        import sys

        if str(skills_dir.parent) not in sys.path:
            sys.path.insert(0, str(skills_dir.parent))

        # Import each skill module (excluding disabled ones) with timeout
        disabled = set()
        skill_import_timeout = 30

        def _import_one(spec, file_path):
            module = importlib.util.module_from_spec(spec)
            sys.modules[file_path.stem] = module
            spec.loader.exec_module(module)

        for file_path in skills_dir.glob("*_skill.py"):
            if file_path.stem in disabled:
                continue

            try:
                import importlib.util
                import sys

                spec = importlib.util.spec_from_file_location(file_path.stem, file_path)
                if spec is None or spec.loader is None:
                    raise ImportError(
                        f"Could not load module spec for {file_path.name}"
                    )
                future = _import_pool.submit(_import_one, spec, file_path)
                future.result(timeout=skill_import_timeout)
            except Exception as e:
                print(f"   ⚠️ Failed to import {file_path.stem}: {e}")

    async def route(
        self, text: str, context: dict[str, Any]
    ) -> str | SkillResponse | None:
        """
        Route user input to appropriate skill.
        Returns: Response string or SkillResponse if skill handled, None if should use LLM Router.
        """
        # Phase 1: Fast keyword matching for SIMPLE intents ONLY.
        matched_name = SkillsRegistry.match_skill(text)
        if matched_name:
            # Check if this is a compound sentence that needs the LLM to orchestrate
            is_compound = self._is_compound(text)
            priority = self._coerce_priority(getattr(matched_name, "priority", 0))

            # Only intercept for ultra-fast commands (like time or media control)
            if self._should_route_direct(
                matched_name.name, priority, text, is_compound
            ):
                print(f"   ⚡ Fast-path match: {matched_name.name}")
                return await self._execute_skill(matched_name.name, text, context)

            print(
                f"   ⏩ Delegating to Agent Router (Priority {priority}, Compound: {is_compound})"
            )

        # We no longer use a dumb 1-skill classifier.
        # By returning None, `main.py` will route this to `llm_router.chat()`
        # which now has access to the full array of Tools natively and can chain them!
        return None

    @staticmethod
    def _coerce_priority(priority: Any) -> int:
        try:
            return int(priority)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _is_compound(text: str) -> bool:
        lowered = (text or "").lower()
        markers = (
            " and then ",
            " after that ",
            " and also ",
            " first do ",
            " then do ",
            " plus ",
        )
        if any(marker in lowered for marker in markers):
            return True
        return any(word in lowered.split() for word in ["and", "then", "also", "plus"])

    def _should_route_direct(
        self, skill_name: str, priority: int, text: str, is_compound: bool
    ) -> bool:
        if is_compound:
            return False
        if priority >= 8:
            return True
        if skill_name in self._DIRECT_ROUTE_SKILLS:
            return True
        return False

    async def execute(self, name: str, text: str, context: dict | None = None) -> str:
        """Public entry point for direct skill invocation (workflows, APIs)."""
        return await self._execute_skill(name, text, context or {})

    async def _execute_skill(
        self, name: str, text: str, context: dict[str, Any]
    ) -> str | SkillResponse | None:
        """Helper to safely execute a skill by name."""
        if self.tool_runner is not None:
            args = {"command": text, "tool_name": text}
            result = await self.tool_runner.execute(
                name,
                args,
                user_intent=text,
                context=context,
            )
            if result.status == "ok":
                return result.data if result.data is not None else result.summary
            return result.to_content_str()

        instance = self._get_skill_instance(name)
        if instance:
            try:
                if name == "browser" and hasattr(instance, "handle_tool_call"):
                    return await instance.handle_tool_call(
                        {"tool_name": text, "command": text}, context
                    )
                return await instance.handle(text, context)
            except Exception as e:
                print(f"   ⚠️ Skill error ({name}): {e}")
        return None

    def get_skill_names(self) -> list[str]:
        """Get list of loaded skill names."""
        return SkillsRegistry.get_skill_names()

    def _get_skill_instance(self, name: str) -> Any | None:
        """Lazy load skill instance (or MCP subprocess proxy) with LRU management."""
        if name in self._instances:
            self._instances.move_to_end(name)
            return self._instances[name]

        # Evict LRU if at capacity
        if len(self._instances) >= self._max_active_skills:
            evicted_name, evicted_instance = self._instances.popitem(last=False)
            self._evict(evicted_name, evicted_instance)

        meta = SkillsRegistry.get_skill(name)
        if not meta:
            return None

        # Route to subprocess proxy if mcp_isolated
        if meta.mcp_isolated and meta.script_path:
            print(f"   🔀 MCP subprocess: launching {name}...")
            try:
                loader = MCPSubprocessLoader(script_path=meta.script_path, name=name)
                proxy = MCPSubprocessProxy(loader)
                self._instances[name] = proxy
                return proxy
            except Exception as e:
                print(f"   ⚠️ MCP subprocess launch failed ({name}): {e}")
                return None

        # Standard in-process lazy load
        print(f"   🛠️ Lazy loading skill: {name}...")
        try:
            instance = SkillsRegistry.create_instance(name)
            if instance:
                if (
                    name == "reminder"
                    and self.tts
                    and hasattr(instance, "set_tts_callback")
                ):
                    instance.set_tts_callback(self.tts)
                self._instances[name] = instance
                return instance
        except Exception as e:
            print(f"   ⚠️ Failed to lazy load {name}: {e}")

        return None

    def _evict(self, name: str, instance: Any) -> None:
        """Properly evict a skill: shutdown subprocess proxies, GC in-process instances."""
        if hasattr(instance, "shutdown"):
            instance.shutdown()  # kills subprocess, frees RAM immediately
            print(f"   💀 MCP subprocess evicted: {name}")
        else:
            print(f"   🧹 LRU evicted: {name}")

    def get_skill_info(self, name: str) -> dict[str, Any] | None:
        """Get information about a specific skill."""
        meta = SkillsRegistry.get_skill(name)
        if meta:
            return {
                "name": meta.name,
                "description": meta.description,
                "keywords": meta.keywords,
                "priority": meta.priority,
                "requires_internet": meta.requires_internet,
                "enabled": meta.enabled,
            }
        return None

    def disable_skill(self, name: str):
        """Disable a skill at runtime."""
        SkillsRegistry.set_enabled(name, False)
        if name in self._instances:
            del self._instances[name]

    def enable_skill(self, name: str):
        """Enable a skill at runtime."""
        SkillsRegistry.set_enabled(name, True)
        if name not in self._instances:
            instance = SkillsRegistry.create_instance(name)
            if instance:
                self._instances[name] = instance
