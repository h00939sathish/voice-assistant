"""
YouTube Music Controller - Background control using ytmusicapi
"""
import logging
from typing import Optional
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from ytmusicapi import YTMusic
    YTMUSIC_AVAILABLE = True
except ImportError:
    YTMUSIC_AVAILABLE = False
    logger.warning("ytmusicapi not installed. Run: pip install ytmusicapi")

class YouTubeMusicController:
    """Controls YouTube Music playback via API"""
    
    def __init__(self):
        self._yt: Optional[YTMusic] = None
        self._available = False
        self._init_client()
        
    def _init_client(self):
        """Initialize YTMusic client"""
        if not YTMUSIC_AVAILABLE:
            return
            
        try:
            # Try to load authenticated headers
            auth_path = Path("oauth.json")
            if auth_path.exists():
                self._yt = YTMusic("oauth.json")
                logger.info("✅ YouTube Music authenticated")
            else:
                # Guest mode (search only, limitation) 
                # For playback control we theoretically rely on browser integration 
                # OR we implement a simple search-and-return-url for the browser to play
                self._yt = YTMusic()
                logger.info("ℹ️ YouTube Music guest mode (search enabled)")
                
            self._available = True
        except Exception as e:
            logger.error(f"Failed to init YTMusic: {e}")
            self._available = False
            
    def search_song(self, query: str) -> Optional[str]:
        """Search for a song and return its videoId"""
        if not self._available:
            return None
            
        try:
            results = self._yt.search(query, filter="songs", limit=1)
            if results:
                return results[0]['videoId']
        except Exception as e:
            logger.error(f"YTM search failed: {e}")
            
        return None
        
    def get_song_url(self, query: str) -> Optional[str]:
        """Get direct URL for a song search"""
        vid_id = self.search_song(query)
        if vid_id:
            return f"https://music.youtube.com/watch?v={vid_id}"
        return None

# Singleton
_ytm_controller = YouTubeMusicController()

def get_ytm_controller():
    return _ytm_controller
