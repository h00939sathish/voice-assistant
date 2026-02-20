# skills/app_integration_skill.py - Deep app integration skill (async-safe)
import asyncio
import logging
import re
import time  # used only in thread-executed functions if needed
from typing import Any, Dict, Optional

from skills.base_skill import BaseSkill
from assistant.app_controller import AppController
from assistant.skill_response import SkillResponse

logger = logging.getLogger("AI_Assistant.AppIntegrationSkill")


class Skill(BaseSkill):
    """
    Skill for opening apps and executing commands within them.
    """

    name = "app_integration"
    keywords = [
        "open", "spotify", "chrome", "edge", "brave", "opera", "discord", "whatsapp", "notepad", "vscode",
        "play", "search", "send", "type", "save", "google", "browse", "look up", "find",
        "message", "mute", "pause", "next", "skip", "previous", "back", "volume"
    ]

    def __init__(self):
        super().__init__()
        self.controller = None
        self._controller_loaded = False
        self.assistant = None

    async def handle(self, text: str, context: Any) -> Optional[str]:
        """
        Standard skill entry point.
        """
        self.assistant = context.get('assistant')
        # context = {'source': 'jarvis_core'} # Already in context
        return await self.on_command(text, context)

    def _get_controller(self):
        if not self._controller_loaded:
            try:
                self.controller = AppController()
                self._controller_loaded = True
            except Exception as e:
                logger.error(f"Failed to load AppController: {e}")
                return None
        return self.controller

    async def on_command(self, text: str, context: Dict[str, Any]) -> str:
        """
        Parse command and route to specific app handler.
        """
        text = text.lower()
        
        if "spotify" in text:
            return await self._handle_spotify_async(text)
        elif "edge" in text:
            return await self._handle_edge_async(text)
        elif "brave" in text:
            return await self._handle_brave_async(text)
        elif "opera" in text:
            return await self._handle_opera_async(text)
        elif "chrome" in text or "google" in text or "browser" in text:
            return await self._handle_chrome_async(text)
        elif "discord" in text:
            return await self._handle_discord_async(text)
        elif "whatsapp" in text:
            return await self._handle_whatsapp_async(text)
        elif "notepad" in text:
            return await self._open_and_execute("notepad", "type " + text, context)
        elif "vscode" in text or "visual studio" in text:
            return await self._open_and_execute("vscode", "open", context)
            
        return None

    # -------------------- Async helpers --------------------
    async def _open_and_execute(self, app_name: str, action: str, context: Dict[str, Any]) -> str:
        """
        Open application (via assistant's open_app) and then execute action via controller.
        Both operations are executed in threads if blocking.
        """
        try:
            controller = self._get_controller()
            if not controller:
                return "App controller unavailable."

            # Launch app if needed
            await asyncio.to_thread(controller.launch_app, app_name)
            # allow app to initialize
            await asyncio.sleep(1.8)

            # controller already loaded above

            # execute controller command in thread (controller is synchronous)
            return await asyncio.to_thread(self._execute_action, app_name, action, controller)

        except Exception as e:
            logger.exception("Error in _open_and_execute: %s", e)
            return f"Failed to execute '{action}' in {app_name}: {e}"

    def _execute_action(self, app_name: str, action: str, controller) -> str:
        """Synchronous executor used inside thread (keeps parsing and controller calls together)."""
        try:
            action = action.lower()

            # Spotify
            if "spotify" in app_name.lower():
                if "play" in action:
                    m = re.search(r"(?:play|search)\s+(?:for\s+)?(.+)", action)
                    if m:
                        query = m.group(1).strip()
                        # Remove trailing "on spotify" if present
                        query = re.sub(r"\s+on\s+spotify['.]?$", "", query, flags=re.I)
                        query = query.strip(" .")
                        if query:
                            return controller.execute_command("spotify", "search", query=query)
                    return controller.execute_command("spotify", "play")
                if "pause" in action:
                    return controller.execute_command("spotify", "pause")
                if "next" in action or "skip" in action:
                    return controller.execute_command("spotify", "next")
                if "previous" in action or "back" in action:
                    return controller.execute_command("spotify", "previous")
                if "volume up" in action or "louder" in action:
                    return controller.execute_command("spotify", "volume_up")
                if "volume down" in action or "quieter" in action:
                    return controller.execute_command("spotify", "volume_down")

            # Chrome / Browser
            if "chrome" in app_name.lower() or "browser" in app_name.lower():
                if "search" in action or "google" in action:
                    m = re.search(r"(?:search|google)\s+(?:for\s+)?(.+)", action)
                    if m:
                        query = m.group(1).strip()
                        return controller.execute_command("chrome", "search", query=query)
                if "go to" in action or "open" in action:
                    m = re.search(r"(?:go to|open)\s+(.+)", action)
                    if m:
                        url = m.group(1).strip()
                        return controller.execute_command("chrome", "go_to", url=url)
                
                # YouTube Music Integration
                if "youtube music" in action and "play" in action:
                    m = re.search(r"play\s+(.+?)\s+on\s+youtube\s+music", action)
                    if m:
                        query = m.group(1).strip()
                        # Use controller to find URL
                        try:
                            from assistant.youtube_music_controller import get_ytm_controller
                            ytm = get_ytm_controller()
                            url = ytm.get_song_url(query)
                            if url:
                                return controller.execute_command("chrome", "go_to", url=url)
                            return f"Could not find '{query}' on YouTube Music"
                        except ImportError:
                            pass
                            
                    # Fallback to generic search
                    return controller.execute_command("chrome", "go_to", url="https://music.youtube.com")

                if "new tab" in action:
                    return controller.execute_command("chrome", "new_tab")
                if "close tab" in action:
                    return controller.execute_command("chrome", "close_tab")
                if "find" in action and "on page" in action:
                    m = re.search(r"find\s+(.+?)\s+on\s+page", action)
                    query = m.group(1).strip() if m else ""
                    return controller.execute_command("chrome", "find_on_page", query=query)

            # Notepad
            if "notepad" in app_name.lower():
                if "type" in action or "write" in action:
                    m = re.search(r"(?:type|write)\s+(.+)", action)
                    if m:
                        text = m.group(1).strip()
                        return controller.execute_command("notepad", "type", text=text)
                if "save" in action:
                    m = re.search(r"save\s+(?:as\s+)?(.+)", action)
                    filename = m.group(1).strip() if m else "document.txt"
                    return controller.execute_command("notepad", "save", filename=filename)

            # VS Code
            if "vscode" in app_name.lower() or "visual studio" in app_name.lower():
                if "new file" in action:
                    return controller.execute_command("vscode", "new_file")
                if "save" in action:
                    return controller.execute_command("vscode", "save")
                if "run" in action:
                    return controller.execute_command("vscode", "run")

            # Discord
            if "discord" in app_name.lower():
                if "send" in action or "message" in action:
                    m = re.search(r"(?:send|message)\s+(.+)", action)
                    if m:
                        message = m.group(1).strip()
                        return controller.execute_command(
                            "discord", "send_message", message=message
                        )
                if "mute" in action:
                    return controller.execute_command("discord", "mute")

            # WhatsApp
            if "whatsapp" in app_name.lower():
                if "send" in action or "message" in action:
                    m = re.search(r"(?:send|message)\s+(.+?)(?:\s+to\s+(.+))?$", action)
                    if m:
                        message = m.group(1).strip()
                        contact = m.group(2).strip() if m.group(2) else None
                        if contact:
                            controller.execute_command(
                                "whatsapp", "search_contact", contact=contact
                            )
                            time.sleep(0.8)
                        return controller.execute_command(
                            "whatsapp", "send_message", message=message
                        )

            return f"I don't know how to '{action}' in {app_name}"
        except Exception as e:
            logger.exception("Error executing action: %s", e)
            return f"Failed to run action: {e}"

    # -------------------- Async wrappers for direct handlers --------------------
    async def _handle_spotify_async(self, cmd: str) -> str:
        """Handle Spotify commands - uses API for background control, falls back to keyboard"""
        # Try Spotify API first (background control - like Siri!)
        try:
            from assistant.spotify_controller import get_spotify_controller
            spotify_api = get_spotify_controller()
            
            if spotify_api.is_available:
                return await asyncio.to_thread(lambda: self._handle_spotify_api(cmd, spotify_api))
        except ImportError:
            pass  # Fall through to keyboard control
        except Exception as e:
            logger.warning(f"Spotify API failed, falling back to keyboard: {e}")
        
        # Fallback: keyboard automation (requires window focus)
        ctr = self._get_controller()
        if not ctr:
            return "App controller unavailable."
        if not await asyncio.to_thread(ctr.is_app_running, "spotify"):
            await asyncio.to_thread(ctr.launch_app, "spotify")
            await asyncio.sleep(3.0)
        return await asyncio.to_thread(lambda: self._handle_spotify_sync(cmd, ctr))
    
    def _handle_spotify_api(self, cmd: str, spotify) -> str:
        """Handle Spotify via Web API (works in background!)"""
        cmd = cmd.lower()
        
        if "open" in cmd and "spotify" in cmd and "play" not in cmd:
            return "Spotify API connected. What would you like to play?"
        
        if "play" in cmd:
            # Extract song/artist name
            m = re.search(r"play\s+(?:music\s+)?(?:search\s+)?(?:for\s+)?(.+)", cmd, re.I)
            if m:
                query = m.group(1).strip()
                query = re.sub(r"\s+on\s+spotify['.]*$", "", query, flags=re.I)
                query = query.strip(" .")
                if query:
                    return spotify.search_and_play(query)
            return spotify.play()
        
        if "pause" in cmd or "stop" in cmd:
            return spotify.pause()
        
        if "next" in cmd or "skip" in cmd:
            return spotify.next_track()
        
        if "previous" in cmd or "back" in cmd:
            return spotify.previous_track()
        
        if "volume" in cmd:
            m = re.search(r"(\d+)", cmd)
            if m:
                vol = int(m.group(1))
                return spotify.set_volume(vol)
            if "up" in cmd or "louder" in cmd:
                return spotify.set_volume(80)
            if "down" in cmd or "quieter" in cmd:
                return spotify.set_volume(30)
        
        return "I couldn't interpret that Spotify command."

    def _handle_spotify_sync(self, cmd: str, controller) -> str:
        """Fallback: Handle Spotify via keyboard automation (requires focus)"""
        try:
            if "open" in cmd and "spotify" in cmd and "play" not in cmd:
                return SkillResponse.with_followup(
                    "Opened Spotify. What would you like to play?",
                    timeout=8.0
                )

            if "play" in cmd:
                m = re.search(r"play\s+(?:music\s+)?(?:search\s+)?(?:for\s+)?(.+)", cmd, re.I)
                if m:
                    query = m.group(1).strip()
                    query = re.sub(r"\s+on\s+spotify\.?$", "", query, flags=re.I)
                    query = query.strip(" .")
                    if query:
                        return controller.execute_command("spotify", "search", query=query)
                return controller.execute_command("spotify", "play")
            if "pause" in cmd:
                return controller.execute_command("spotify", "pause")
            if "next" in cmd or "skip" in cmd:
                return controller.execute_command("spotify", "next")
            if "previous" in cmd or "back" in cmd:
                return controller.execute_command("spotify", "previous")
            if "volume up" in cmd or "louder" in cmd:
                return controller.execute_command("spotify", "volume_up")
            if "volume down" in cmd or "quieter" in cmd:
                return controller.execute_command("spotify", "volume_down")
        except Exception as e:
            logger.exception("Spotify handler failed: %s", e)
            return "Spotify action failed."
        return "I couldn't interpret that Spotify command."


    async def _handle_chrome_async(self, cmd: str) -> str:
        ctr = self._get_controller()
        if not ctr:
            return "App controller unavailable."
        if not await asyncio.to_thread(ctr.is_app_running, "chrome"):
            await asyncio.to_thread(ctr.launch_app, "chrome")
            await asyncio.sleep(1.6)
        return await asyncio.to_thread(lambda: self._handle_chrome_sync(cmd, ctr))

    def _handle_chrome_sync(self, cmd: str, controller) -> str:
        try:
            if "open" in cmd and ("chrome" in cmd or "browser" in cmd) and "search" not in cmd and "go to" not in cmd:
                return SkillResponse.with_followup(
                    "Opened Chrome. What would you like to search?",
                    timeout=8.0
                )

            if "search" in cmd or "google" in cmd:
                m = re.search(r"(?:search|google)\s+(?:for\s+)?(.+)", cmd, re.I)
                if m:
                    query = m.group(1).strip()
                    return controller.execute_command("chrome", "search", query=query)
            if "new tab" in cmd:
                return controller.execute_command("chrome", "new_tab")
            if "close tab" in cmd:
                return controller.execute_command("chrome", "close_tab")
            if "find" in cmd and "on page" in cmd:
                m = re.search(r"find\s+(.+?)\s+on\s+page", cmd, re.I)
                query = m.group(1).strip() if m else ""
                return controller.execute_command("chrome", "find_on_page", query=query)
        except Exception as e:
            logger.exception("Chrome handler failed: %s", e)
            return "Chrome action failed."
        return "I couldn't interpret that Chrome command."

    async def _handle_edge_async(self, cmd: str) -> str:
        ctr = self._get_controller()
        if not ctr:
            return "App controller unavailable."
        if not await asyncio.to_thread(ctr.is_app_running, "msedge"):
            await asyncio.to_thread(ctr.launch_app, "edge")
            await asyncio.sleep(1.6)
        return await asyncio.to_thread(lambda: self._handle_edge_sync(cmd, ctr))

    def _handle_edge_sync(self, cmd: str, controller) -> str:
        try:
            if "open" in cmd and "edge" in cmd and "search" not in cmd and "go to" not in cmd:
                return SkillResponse.with_followup(
                    "Opened Microsoft Edge. What would you like to search?",
                    timeout=8.0
                )

            if "search" in cmd or "google" in cmd:
                m = re.search(r"(?:search|google)\s+(?:for\s+)?(.+)", cmd, re.I)
                if m:
                    query = m.group(1).strip()
                    return controller.execute_command("edge", "search", query=query)
            if "new tab" in cmd:
                return controller.execute_command("edge", "new_tab")
            if "close tab" in cmd:
                return controller.execute_command("edge", "close_tab")
            if "find" in cmd and "on page" in cmd:
                m = re.search(r"find\s+(.+?)\s+on\s+page", cmd, re.I)
                query = m.group(1).strip() if m else ""
                return controller.execute_command("edge", "find_on_page", query=query)
        except Exception as e:
            logger.exception("Edge handler failed: %s", e)
            return "Edge action failed."
        return "I couldn't interpret that Edge command."

    async def _handle_brave_async(self, cmd: str) -> str:
        ctr = self._get_controller()
        if not ctr:
            return "App controller unavailable."
        if not await asyncio.to_thread(ctr.is_app_running, "brave"):
            await asyncio.to_thread(ctr.launch_app, "brave")
            await asyncio.sleep(1.6)
        return await asyncio.to_thread(lambda: self._handle_brave_sync(cmd, ctr))

    def _handle_brave_sync(self, cmd: str, controller) -> str:
        try:
            if "open" in cmd and "brave" in cmd and "search" not in cmd and "go to" not in cmd:
                return SkillResponse.with_followup(
                    "Opened Brave browser. What would you like to search?",
                    timeout=8.0
                )

            if "search" in cmd or "google" in cmd:
                m = re.search(r"(?:search|google)\s+(?:for\s+)?(.+)", cmd, re.I)
                if m:
                    query = m.group(1).strip()
                    return controller.execute_command("brave", "search", query=query)
            if "new tab" in cmd:
                return controller.execute_command("brave", "new_tab")
            if "close tab" in cmd:
                return controller.execute_command("brave", "close_tab")
            if "find" in cmd and "on page" in cmd:
                m = re.search(r"find\s+(.+?)\s+on\s+page", cmd, re.I)
                query = m.group(1).strip() if m else ""
                return controller.execute_command("brave", "find_on_page", query=query)
        except Exception as e:
            logger.exception("Brave handler failed: %s", e)
            return "Brave action failed."
        return "I couldn't interpret that Brave command."

    async def _handle_opera_async(self, cmd: str) -> str:
        ctr = self._get_controller()
        if not ctr:
            return "App controller unavailable."
        if not await asyncio.to_thread(ctr.is_app_running, "opera"):
            await asyncio.to_thread(ctr.launch_app, "opera")
            await asyncio.sleep(1.6)
        return await asyncio.to_thread(lambda: self._handle_opera_sync(cmd, ctr))

    def _handle_opera_sync(self, cmd: str, controller) -> str:
        try:
            if "open" in cmd and "opera" in cmd and "search" not in cmd and "go to" not in cmd:
                return SkillResponse.with_followup(
                    "Opened Opera browser. What would you like to search?",
                    timeout=8.0
                )

            if "search" in cmd or "google" in cmd:
                m = re.search(r"(?:search|google)\s+(?:for\s+)?(.+)", cmd, re.I)
                if m:
                    query = m.group(1).strip()
                    return controller.execute_command("opera", "search", query=query)
            if "new tab" in cmd:
                return controller.execute_command("opera", "new_tab")
            if "close tab" in cmd:
                return controller.execute_command("opera", "close_tab")
            if "find" in cmd and "on page" in cmd:
                m = re.search(r"find\s+(.+?)\s+on\s+page", cmd, re.I)
                query = m.group(1).strip() if m else ""
                return controller.execute_command("opera", "find_on_page", query=query)
        except Exception as e:
            logger.exception("Opera handler failed: %s", e)
            return "Opera action failed."
        return "I couldn't interpret that Opera command."

    async def _handle_discord_async(self, cmd: str) -> str:
        ctr = self._get_controller()
        if not ctr:
            return "App controller unavailable."
        if not await asyncio.to_thread(ctr.is_app_running, "discord"):
            await asyncio.to_thread(ctr.launch_app, "discord")
            await asyncio.sleep(1.6)
        return await asyncio.to_thread(lambda: self._handle_discord_sync(cmd, ctr))

    def _handle_discord_sync(self, cmd: str, controller) -> str:
        try:
            if "open" in cmd and "discord" in cmd and "send" not in cmd and "message" not in cmd:
                return SkillResponse.with_followup(
                    "Opened Discord. What would you like me to do?",
                    timeout=8.0
                )

            if "mute" in cmd:
                return controller.execute_command("discord", "mute")
            if "send" in cmd or "message" in cmd:
                m = re.search(r"(?:send|message)\s+(.+?)(?:\s+on discord)?$", cmd, re.I)
                if m:
                    message = m.group(1).strip()
                    return controller.execute_command("discord", "send_message", message=message)
        except Exception as e:
            logger.exception("Discord handler failed: %s", e)
            return "Discord action failed."
        return "I couldn't interpret that Discord command."

    async def _handle_whatsapp_async(self, cmd: str) -> str:
        ctr = self._get_controller()
        if not ctr:
            return "App controller unavailable."
        if not await asyncio.to_thread(ctr.is_app_running, "whatsapp"):
            await asyncio.to_thread(ctr.launch_app, "whatsapp")
            await asyncio.sleep(2.4)
        return await asyncio.to_thread(lambda: self._handle_whatsapp_sync(cmd, ctr))

    def _handle_whatsapp_sync(self, cmd: str, controller) -> str:
        try:
            if "open" in cmd and "whatsapp" in cmd and "send" not in cmd and "message" not in cmd:
                return SkillResponse.with_followup(
                    "Opened WhatsApp. Who would you like to message?",
                    timeout=10.0
                )

            if "send" in cmd or "message" in cmd:
                m = re.search(
                    r"(?:send|message)\s+(.+?)(?:\s+to\s+(.+?))?(?:\s+on whatsapp)?$", cmd, re.I
                )
                if m:
                    message = m.group(1).strip()
                    contact = m.group(2).strip() if m.group(2) else None
                    if contact:
                        controller.execute_command("whatsapp", "search_contact", contact=contact)
                        time.sleep(0.8)
                    return controller.execute_command("whatsapp", "send_message", message=message)
        except Exception as e:
            logger.exception("WhatsApp handler failed: %s", e)
            return "WhatsApp action failed."
        return "I couldn't interpret that WhatsApp command."

    # Utilities used by plugin system to describe the skill
    def help(self) -> str:
        return """
App Integration Skill - Natural Commands:
• "open spotify and play [song]"
• "play [song] on spotify"
• "search google for [query]"
• "find [text] on page"
• "send [message] on discord"
• "send [message] to [contact] on whatsapp"
"""
