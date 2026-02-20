"""
Clipboard Skill - Read/Write to system clipboard
"""
import pyperclip
import logging
from typing import Dict, Any

# Add project root to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


logger = logging.getLogger(__name__)

class ClipboardSkill:
    """
    Interacts with the system clipboard.
    """
    
    def __init__(self):
        self.keywords = ["clipboard", "copy", "paste"]

    async def handle(self, text: str, context: Dict[str, Any]) -> str:
        """Handle clipboard commands"""
        text = text.lower()
        
        # Read clipboard
        if "read" in text or "what is on" in text or "what's on" in text:
            try:
                content = pyperclip.paste()
                if not content:
                    return "The clipboard is empty."
                
                # Truncate if too long
                preview = content[:200] + "..." if len(content) > 200 else content
                return f"Here's what's on your clipboard: {preview}"
            except Exception as e:
                logger.error(f"Clipboard read error: {e}")
                return "I couldn't read the clipboard."

        # Paste (simulate typing)
        # "Paste this" or "Type clipboard"
        if "paste" in text or "type" in text:
            try:
                import pyautogui
                content = pyperclip.paste()
                if not content:
                    return "Clipboard is empty, nothing to paste."
                
                # Type it out
                pyautogui.write(content)
                return "Pasting clipboard content..."
            except Exception as e:
                logger.error(f"Clipboard paste error: {e}")
                return "I couldn't paste the content."
                
        # Copy logic is usually handled by "Copy that" referring to the LAST assistant response
        # But we need access to history for that.
        # For now, we'll support "Copy [text]"
        if "copy" in text:
            # check if they want to copy specific text
            import re
            m = re.search(r"copy\s+(?:saying\s+)?(.+)", text)
            if m:
                content = m.group(1).strip()
                pyperclip.copy(content)
                return f"Copied to clipboard: {content}"
            
        return "You can say 'Read my clipboard' or 'Paste clipboard'."
