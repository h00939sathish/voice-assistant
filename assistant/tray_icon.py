"""
System Tray Icon - Background control for the assistant
"""
import threading
import logging
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image, ImageDraw
    TRAY_AVAILABLE = True
except ImportError:
    TRAY_AVAILABLE = False
    pystray = None

logger = logging.getLogger(__name__)


def create_icon_image(color: str = "#4A90D9", size: int = 64) -> "Image.Image":
    """Create a simple circular icon"""
    image = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    
    # Draw filled circle
    margin = 4
    draw.ellipse(
        [margin, margin, size - margin, size - margin],
        fill=color,
        outline="#FFFFFF",
        width=2
    )
    return image


class TrayIcon:
    """
    System tray icon with control menu.
    """
    
    def __init__(self, 
                 on_pause: Optional[Callable] = None,
                 on_resume: Optional[Callable] = None,
                 on_quit: Optional[Callable] = None):
        self.on_pause = on_pause
        self.on_resume = on_resume
        self.on_quit = on_quit
        self._icon: Optional["pystray.Icon"] = None
        self._thread: Optional[threading.Thread] = None
        self._paused = False
        
        if not TRAY_AVAILABLE:
            logger.warning("pystray not installed. Tray icon disabled.")

    def start(self):
        """Start tray icon in background thread"""
        if not TRAY_AVAILABLE:
            return
            
        self._thread = threading.Thread(target=self._run, daemon=True, name="TrayIcon")
        self._thread.start()
        logger.info("   🔲 System tray icon started")

    def _run(self):
        """Run pystray event loop"""
        menu = pystray.Menu(
            pystray.MenuItem("Pause", self._toggle_pause, checked=lambda item: self._paused),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self._quit)
        )
        
        self._icon = pystray.Icon(
            name="BuddyAssistant",
            icon=create_icon_image(),
            title="Buddy Assistant",
            menu=menu
        )
        self._icon.run()

    def _toggle_pause(self):
        """Toggle pause state"""
        self._paused = not self._paused
        if self._paused:
            logger.info("   ⏸️ Assistant paused")
            if self.on_pause:
                self.on_pause()
        else:
            logger.info("   ▶️ Assistant resumed")
            if self.on_resume:
                self.on_resume()
        
        # Update icon color
        if self._icon:
            color = "#888888" if self._paused else "#4A90D9"
            self._icon.icon = create_icon_image(color)

    def _quit(self):
        """Handle quit action"""
        logger.info("   👋 Quit requested from tray")
        if self._icon:
            self._icon.stop()
        if self.on_quit:
            self.on_quit()

    def stop(self):
        """Stop the tray icon"""
        if self._icon:
            self._icon.stop()

    @property
    def is_paused(self) -> bool:
        return self._paused
