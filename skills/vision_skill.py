"""
Vision Skill - Screenshot capture and AI analysis using Gemini Vision
"""

import base64
import io
import logging
from typing import Any

from skills.base_skill import BaseSkill, skill

logger = logging.getLogger(__name__)


@skill(
    name="vision",
    keywords=[
        "what's on my screen",
        "screenshot",
        "analyze screen",
        "read screen",
        "describe screen",
        "screen",
        "what do you see",
        "look at my screen",
    ],
    description="Captures screenshot and analyzes it with Gemini Vision AI",
    priority=6,
    requires_internet=True,
)
class VisionSkill(BaseSkill):
    """Captures screenshots and analyzes them using Gemini Vision API."""

    def __init__(self):
        super().__init__()
        self._client = None
        self._available = False

    def _ensure_client(self):
        if self._client:
            return True
        try:
            from config import GEMINI_API_KEY

            if not GEMINI_API_KEY:
                return False
            from google import genai

            self._client = genai.Client(api_key=GEMINI_API_KEY)
            self._available = True
            return True
        except Exception as e:
            logger.error(f"Failed to init Gemini client: {e}")
            return False

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        text = text.lower()

        if not self._ensure_client():
            return (
                "Vision is not available. Please set GEMINI_API_KEY in your .env file."
            )

        # Capture screenshot
        try:
            from PIL import ImageGrab

            screenshot = ImageGrab.grab()
            img_buffer = io.BytesIO()
            screenshot.save(img_buffer, format="PNG")
            img_bytes = img_buffer.getvalue()
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Screenshot failed: {e}")
            return "I couldn't capture the screen."

        # Build prompt based on user question
        if "read" in text or "text" in text:
            prompt = "Read and transcribe all visible text on this screen. Be thorough."
        elif "describe" in text:
            prompt = "Describe what you see on this screen in detail."
        elif "help" in text or "how" in text:
            prompt = (
                "Look at this screen and help the user with what they're working on."
            )
        elif "code" in text or "error" in text:
            prompt = "Analyze this screen for any code or error messages. Explain what you see and suggest fixes."
        else:
            prompt = (
                "Briefly describe what's on this screen. Focus on the main content."
            )

        # Try multiple models with retry on rate limit
        models = ["gemini-2.0-flash", "gemini-1.5-flash", "gemini-2.0-flash-lite"]
        contents = [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": img_b64}},
                ]
            }
        ]

        for model in models:
            try:
                response = self._client.models.generate_content(
                    model=model, contents=contents
                )
                return response.text
            except Exception as e:
                error_str = str(e)
                if "429" in error_str or "RESOURCE_EXHAUSTED" in error_str:
                    logger.warning(f"Rate limited on {model}, trying next model...")
                    continue
                logger.error(f"Vision analysis failed on {model}: {e}")
                return f"I captured the screen but couldn't analyze it: {e}"

        # All models rate-limited — retry once after delay
        import asyncio

        logger.info("All models rate-limited, retrying in 25s...")
        await asyncio.sleep(25)
        try:
            response = self._client.models.generate_content(
                model=models[0], contents=contents
            )
            return response.text
        except Exception as e:
            logger.error(f"Vision retry failed: {e}")
            return "Gemini API quota exhausted. Please wait a minute and try again."
