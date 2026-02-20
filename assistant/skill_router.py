"""
Skill Router - Routes commands to skills using the registry.
Hybrid approach: keyword matching first, then LLM classification.
"""
from typing import Dict, Any, List, Optional, Union
from pathlib import Path
from collections import OrderedDict

try:
    import ollama
except ImportError:
    ollama = None

from assistant.skills_registry import SkillsRegistry
from assistant.skill_response import SkillResponse
from assistant.interfaces import ILLMProvider, ITTSProvider


class SkillRouter:
    """
    Routes user input to appropriate skills.
    1. Fast keyword matching via registry (~1ms)
    2. LLM classification for ambiguous queries (~150ms)
    """

    def __init__(self, llm_router: ILLMProvider = None, tts: ITTSProvider = None, skills_dir: str = None):
        self.llm = llm_router
        self.tts = tts
        self._classifier_model = "gemma:2b"  # Fast, small model for classification
        self._instances = OrderedDict()  # LRU Cache for skill instances
        self._max_active_skills = 5

    def load_skills(self):
        """Load all registered skills from the registry."""
        print("📦 Loading skills...")

        # Import all skill modules to trigger registration
        self._import_all_skills()
        
        # Log discovered skills (but don't instantiate yet)
        skills = SkillsRegistry.get_all_skills()
        print(f"   Note: {len(skills)} skills registered (Lazy Loading Enabled)")
        for name, meta in skills.items():
             print(f"   - {name}: {meta.description[:50]}...")

    def _import_all_skills(self):
        """Import all skill modules to trigger @skill decorators."""
        skills_dir = Path(__file__).parent.parent / "skills"

        if not skills_dir.exists():
            print(f"   ⚠️ Skills directory not found: {skills_dir}")
            return

        # Skills to skip if not configured
        SKIP_SKILLS = {
            "mcp_skill": True,  # MCP often unused
        }

        # Import each skill module
        for file_path in skills_dir.glob("*_skill.py"):
            module_name = file_path.stem  # e.g., "time_skill"
            
            # Skip disabled skills
            if module_name in SKIP_SKILLS:
                print(f"   ⏭️ Skipping: {module_name} (disabled)")
                continue
                
            try:
                # Dynamic import
                import importlib.util
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)

                # Add skills dir to path for relative imports within skills
                import sys
                skills_parent = str(skills_dir.parent)
                if skills_parent not in sys.path:
                    sys.path.insert(0, skills_parent)

                spec.loader.exec_module(module)
            except Exception as e:
                print(f"   ⚠️ Failed to import {module_name}: {e}")

    async def route(self, text: str, context: Dict[str, Any]) -> Optional[Union[str, SkillResponse]]:
        """
        Route user input to appropriate skill.

        Returns:
            Response string or SkillResponse if skill handled, None if should use LLM
        """
        # Phase 1: Fast keyword matching via registry
        matched_metadata = SkillsRegistry.match_skill(text)

        if matched_metadata:
            print(f"   🎯 Keyword match: {matched_metadata.name}")
            instance = self._get_skill_instance(matched_metadata.name)
            if instance:
                try:
                    return await instance.handle(text, context)
                except Exception as e:
                    print(f"   ⚠️ Skill error: {e}")
                    return None

        # Phase 2: LLM classification for ambiguous queries
        classified_name = await self._llm_classify(text)

        if classified_name:
            print(f"   🧠 LLM classified: {classified_name}")
            instance = self._get_skill_instance(classified_name)
            if instance:
                try:
                    return await instance.handle(text, context)
                except Exception as e:
                    print(f"   ⚠️ Skill error: {e}")
                    return None

        # No skill matched - let main LLM handle it
        return None

    async def _llm_classify(self, text: str) -> Optional[str]:
        """Use small LLM to classify intent."""
        if not self._instances or ollama is None:
            return None

        # Build skill list from registry
        skill_list = ", ".join([
            f"{name}: {meta.description}"
            for name, meta in SkillsRegistry.get_all_skills().items()
            if meta.enabled
        ])

        prompt = f"""Classify this user request into one of these skills, or respond "general" if none match.
Skills: {skill_list}

User: "{text}"
Respond with ONLY the skill name or "general". Nothing else."""

        try:
            response = ollama.chat(
                model=self._classifier_model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 20}  # Very short response
            )
            result = response['message']['content'].strip().lower()

            # Clean up response
            result = result.replace('"', '').replace("'", "").strip()

            if result == "general":
                return None
            
            # Verify skill exists in registry
            return result if SkillsRegistry.get_skill(result) else None

        except Exception as e:
            print(f"   ⚠️ Classification failed: {e}")
            return None

    def get_skill_names(self) -> List[str]:
        """Get list of loaded skill names."""
        return SkillsRegistry.get_skill_names()

    def _get_skill_instance(self, name: str) -> Optional[Any]:
        """Lazy load skill instance with LRU management."""
        if name in self._instances:
            # Move to end (most recently used)
            self._instances.move_to_end(name)
            return self._instances[name]
            
        # Check limit and evict LRU if needed
        if len(self._instances) >= self._max_active_skills:
            evicted_name, _ = self._instances.popitem(last=False)
            print(f"   🧹 LRU: Evicted skill {evicted_name} to save memory")

        print(f"   🛠️ Lazy loading skill: {name}...")
        try:
            instance = SkillsRegistry.create_instance(name)
            if instance:
                # Inject TTS if needed
                if name == "reminder" and self.tts and hasattr(instance, "set_tts_callback"):
                    instance.set_tts_callback(self.tts)
                
                self._instances[name] = instance
                return instance
        except Exception as e:
            print(f"   ⚠️ Failed to lazy load {name}: {e}")
            
        return None

    def get_skill_info(self, name: str) -> Optional[Dict[str, Any]]:
        """Get information about a specific skill."""
        meta = SkillsRegistry.get_skill(name)
        if meta:
            return {
                "name": meta.name,
                "description": meta.description,
                "keywords": meta.keywords,
                "priority": meta.priority,
                "requires_internet": meta.requires_internet,
                "enabled": meta.enabled
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
