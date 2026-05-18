"""
Spotify API Controller - Background control of Spotify using the Web API
"""

import logging
import os
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Add parent to path for config import
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth

    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False
    logger.warning("spotipy not installed. Run: pip install spotipy")

from config import SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET, SPOTIFY_REDIRECT_URI


class SpotifyController:
    """Controls Spotify playback via the Web API (works in background!)"""

    def __init__(self):
        self._sp: spotipy.Spotify | None = None
        self._available = False
        self._init_client()

    def _init_client(self):
        """Initialize Spotify client with OAuth"""
        if not SPOTIPY_AVAILABLE:
            logger.warning("Spotipy library not available")
            return

        if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
            logger.warning("Spotify API credentials not configured")
            return

        try:
            # OAuth with required scopes for playback control
            scope = "user-read-playback-state user-modify-playback-state user-read-currently-playing"

            auth_manager = SpotifyOAuth(
                client_id=SPOTIFY_CLIENT_ID,
                client_secret=SPOTIFY_CLIENT_SECRET,
                redirect_uri=SPOTIFY_REDIRECT_URI,
                scope=scope,
                cache_path=str(Path.home() / ".buddy_spotify_cache"),
            )

            self._sp = spotipy.Spotify(auth_manager=auth_manager)
            self._available = True
            logger.info("✅ Spotify API connected!")

        except Exception as e:
            logger.exception(f"Failed to initialize Spotify API: {e}")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available and self._sp is not None

    def _get_active_device(self) -> str | None:
        """Get the ID of an active Spotify device"""
        if not self.is_available:
            return None
        try:
            devices = self._sp.devices()
            if devices and devices.get("devices"):
                # Prefer active device, otherwise first available
                for device in devices["devices"]:
                    if device.get("is_active"):
                        return device["id"]
                # No active device, return first one
                return devices["devices"][0]["id"]
        except Exception as e:
            logger.error(f"Failed to get devices: {e}")
        return None

    def search_and_play(self, query: str) -> str:
        """Search for a track and play it (BACKGROUND - no window focus needed!)"""
        if not self.is_available:
            return "Spotify API not available. Check credentials."

        try:
            # Search for the track
            results = self._sp.search(q=query, type="track", limit=1)
            tracks = results.get("tracks", {}).get("items", [])

            if not tracks:
                return f"No results found for '{query}'"

            track = tracks[0]
            track_uri = track["uri"]
            track_name = track["name"]
            artist_name = (
                track["artists"][0]["name"] if track.get("artists") else "Unknown"
            )

            # Get device to play on
            device_id = self._get_active_device()

            # Start playback
            self._sp.start_playback(device_id=device_id, uris=[track_uri])

            return f"Playing '{track_name}' by {artist_name}"

        except spotipy.exceptions.SpotifyException as e:
            err = str(e)
            if "NO_ACTIVE_DEVICE" in err or "404" in err:
                return (
                    "No active Spotify device. Please open Spotify on any device first."
                )
            if "PREMIUM_REQUIRED" in err or "403" in err:
                # Re-raise so caller can fall back to keyboard automation
                raise RuntimeError("PREMIUM_REQUIRED")
            logger.error(f"Spotify API error: {e}")
            raise RuntimeError(f"Spotify API error: {e}")
        except RuntimeError:
            raise
        except Exception as e:
            logger.error(f"Failed to search and play: {e}")
            raise RuntimeError(f"Failed to play: {e}")

    def play(self) -> str:
        """Resume playback"""
        if not self.is_available:
            return "Spotify API not available"
        try:
            device_id = self._get_active_device()
            self._sp.start_playback(device_id=device_id)
            return "Resumed playback"
        except Exception as e:
            logger.error(f"Play failed: {e}")
            return "Failed to resume playback"

    def pause(self) -> str:
        """Pause playback"""
        if not self.is_available:
            return "Spotify API not available"
        try:
            self._sp.pause_playback()
            return "Paused playback"
        except Exception as e:
            logger.error(f"Pause failed: {e}")
            return "Failed to pause"

    def next_track(self) -> str:
        """Skip to next track"""
        if not self.is_available:
            return "Spotify API not available"
        try:
            self._sp.next_track()
            return "Skipped to next track"
        except Exception as e:
            logger.error(f"Next track failed: {e}")
            return "Failed to skip"

    def previous_track(self) -> str:
        """Go to previous track"""
        if not self.is_available:
            return "Spotify API not available"
        try:
            self._sp.previous_track()
            return "Playing previous track"
        except Exception as e:
            logger.error(f"Previous track failed: {e}")
            return "Failed to go back"

    def set_volume(self, volume_percent: int) -> str:
        """Set volume (0-100)"""
        if not self.is_available:
            return "Spotify API not available"
        try:
            volume_percent = max(0, min(100, volume_percent))
            self._sp.volume(volume_percent)
            return f"Volume set to {volume_percent}%"
        except Exception as e:
            logger.error(f"Set volume failed: {e}")
            return "Failed to set volume"

    def get_current_track(self) -> dict[str, Any] | None:
        """Get currently playing track info"""
        if not self.is_available:
            return None
        try:
            current = self._sp.current_playback()
            if current and current.get("item"):
                item = current["item"]
                return {
                    "name": item.get("name"),
                    "artist": item["artists"][0]["name"]
                    if item.get("artists")
                    else "Unknown",
                    "album": item.get("album", {}).get("name"),
                    "is_playing": current.get("is_playing", False),
                }
        except Exception as e:
            logger.error(f"Get current track failed: {e}")
        return None


# Singleton instance
_spotify_controller: SpotifyController | None = None


def get_spotify_controller() -> SpotifyController:
    """Get or create the Spotify controller singleton"""
    global _spotify_controller
    if _spotify_controller is None:
        _spotify_controller = SpotifyController()
    return _spotify_controller
