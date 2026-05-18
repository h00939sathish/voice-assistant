"""
Clipboard Skill - Read/Write to system clipboard
"""

import logging
import re
from typing import Any

from skills.base_skill import BaseSkill, skill

logger = logging.getLogger(__name__)


@skill(
    name="clipboard",
    keywords=["clipboard", "copy", "paste", "read clipboard", "what's on my clipboard"],
    description="Read, copy, and paste system clipboard content",
    priority=4,
)
class ClipboardSkill(BaseSkill):
    """Interacts with the system clipboard."""

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        text = text.lower()

        # Read clipboard
        if "read" in text or "what is on" in text or "what's on" in text:
            try:
                import pyperclip

                content = pyperclip.paste()
                if not content:
                    return "The clipboard is empty."
                preview = content[:200] + "..." if len(content) > 200 else content
                return f"Here's what's on your clipboard: {preview}"
            except Exception as e:
                logger.error(f"Clipboard read error: {e}")
                return "I couldn't read the clipboard."

        # Paste (simulate typing)
        if "paste" in text or "type" in text:
            try:
                import pyautogui
                import pyperclip

                content = pyperclip.paste()
                if not content:
                    return "Clipboard is empty, nothing to paste."
                pyautogui.write(content)
                return "Pasting clipboard content..."
            except Exception as e:
                logger.error(f"Clipboard paste error: {e}")
                return "I couldn't paste the content."

        # Copy specific text
        if "copy" in text:
            m = re.search(r"copy\s+(?:saying\s+)?(.+)", text)
            if m:
                import pyperclip

                content = m.group(1).strip()
                pyperclip.copy(content)
                return f"Copied to clipboard: {content}"

        return "You can say 'Read my clipboard' or 'Paste clipboard'."
