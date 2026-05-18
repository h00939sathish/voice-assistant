"""
Screen Awareness Skill - User-facing skill to query what's on screen.
"""

from assistant.skills_registry import skill
from skills.base_skill import BaseSkill


@skill(
    name="screen_awareness",
    keywords=[
        "screen",
        "see",
        "display",
        "what's on my screen",
        "describe screen",
        "read screen",
        "what do you see",
        "screen text",
    ],
    description="Describe what's currently visible on the user's screen using desktop awareness.",
    priority=6,
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Optional: what to look for on the screen",
            }
        },
        "required": [],
    },
)
class ScreenAwarenessSkill(BaseSkill):
    async def handle(self, text: str, context: dict) -> str:
        return await self.handle_tool_call({"query": text}, context)

    async def handle_tool_call(self, args: dict, context: dict) -> str:
        try:
            from assistant.desktop_awareness import DesktopAwareness

            # Try to get the global instance from the proactive engine or create one
            awareness = getattr(self, "_awareness", None)
            if not awareness:
                awareness = DesktopAwareness(
                    interval=10, ocr_enabled=True, history_size=3
                )
                self._awareness = awareness

            if not awareness.available:
                return "Desktop awareness is not available. Install 'mss' package: pip install mss"

            # If not running, do a one-shot capture
            if not awareness._running:
                awareness.start()
                import asyncio

                await asyncio.sleep(2)  # Wait for first capture

            context_text = awareness.get_screen_context()

            query = args.get("query", "")
            if query and "search" not in query.lower():
                return f"Here's what I see on your screen:\n\n{context_text}"

            return context_text

        except ImportError:
            return "Desktop awareness module not available."
        except Exception as e:
            return f"Error reading screen: {e}"
