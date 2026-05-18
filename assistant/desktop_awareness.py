"""
Desktop Awareness - Periodic screenshot + OCR engine for screen context.

Captures the desktop at configurable intervals, optionally runs OCR,
and exposes the current screen text to other modules (proactive engine, skills).
"""

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass
from datetime import datetime

logger = logging.getLogger(__name__)

try:
    import mss

    _MSS_AVAILABLE = True
except ImportError:
    _MSS_AVAILABLE = False

try:
    from PIL import Image

    _PIL_AVAILABLE = True
except ImportError:
    _PIL_AVAILABLE = False

try:
    import pytesseract

    _OCR_AVAILABLE = True
except Exception:
    _OCR_AVAILABLE = False


@dataclass
class ScreenCapture:
    """A single screen capture with optional OCR text."""

    timestamp: datetime
    ocr_text: str = ""
    width: int = 0
    height: int = 0
    has_ocr: bool = False


class DesktopAwareness:
    """
    Background engine that periodically captures the desktop and runs OCR.

    Usage:
        awareness = DesktopAwareness(interval=10, ocr_enabled=True)
        awareness.start()
        ...
        context = awareness.get_screen_context()
        awareness.stop()
    """

    _ERROR_KEYWORDS = [
        "error",
        "exception",
        "failed",
        "crash",
        "fatal",
        "not responding",
        "stopped working",
        "access denied",
        "permission denied",
        "timed out",
        "connection refused",
    ]

    _STRUGGLE_KEYWORDS = [
        "loading",
        "please wait",
        "buffering",
        "connecting",
        "retrying",
        "attempting",
        "searching",
    ]

    def __init__(
        self,
        interval: float = 10.0,
        ocr_enabled: bool = True,
        history_size: int = 3,
    ):
        self.interval = max(2.0, interval)
        self.ocr_enabled = ocr_enabled and _OCR_AVAILABLE and _PIL_AVAILABLE
        self.history_size = max(1, history_size)

        self._history: deque[ScreenCapture] = deque(maxlen=self.history_size)
        self._lock = threading.Lock()
        self._running = False
        self._thread: threading.Thread | None = None

        if not _MSS_AVAILABLE:
            logger.warning("   ⚠️ mss not installed — desktop awareness disabled")
        if not _OCR_AVAILABLE and ocr_enabled:
            logger.warning("   ⚠️ pytesseract not available — OCR disabled")

    @property
    def available(self) -> bool:
        return _MSS_AVAILABLE

    def start(self) -> None:
        """Start background capture thread."""
        if not _MSS_AVAILABLE:
            return
        if self._running:
            return

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop, daemon=True, name="DesktopAwareness"
        )
        self._thread.start()
        logger.info(
            f"   🖥️ Desktop Awareness started (interval={self.interval}s, OCR={self.ocr_enabled})"
        )

    def stop(self) -> None:
        """Stop background capture thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)
            self._thread = None
        logger.info("   🖥️ Desktop Awareness stopped")

    def _capture_loop(self) -> None:
        """Background loop: capture → OCR → store."""
        while self._running:
            try:
                capture = self._take_capture()
                if capture:
                    with self._lock:
                        self._history.append(capture)
            except Exception as e:
                logger.debug(f"Desktop capture error: {e}")

            # Sleep in small increments so stop() is responsive
            for _ in range(int(self.interval * 10)):
                if not self._running:
                    return
                time.sleep(0.1)

    def _take_capture(self) -> ScreenCapture | None:
        """Capture primary monitor screenshot and optionally run OCR."""
        try:
            with mss.mss() as sct:
                monitor = sct.monitors[1]  # Primary monitor
                screenshot = sct.grab(monitor)

                capture = ScreenCapture(
                    timestamp=datetime.now(),
                    width=screenshot.width,
                    height=screenshot.height,
                )

                if self.ocr_enabled:
                    # Convert to PIL Image for pytesseract
                    img = Image.frombytes(
                        "RGB", screenshot.size, screenshot.bgra, "raw", "BGRX"
                    )
                    # Resize down for faster OCR (half resolution)
                    w, h = img.size
                    img = img.resize((w // 2, h // 2), Image.LANCZOS)
                    text = pytesseract.image_to_string(img, timeout=5)
                    capture.ocr_text = text.strip()
                    capture.has_ocr = True

                return capture
        except Exception as e:
            logger.debug(f"Screenshot capture failed: {e}")
            return None

    def get_screen_context(self) -> str:
        """
        Get current screen context as a formatted string.
        Returns OCR text from the most recent capture.
        """
        with self._lock:
            if not self._history:
                return "No screen data available."

            latest = self._history[-1]
            age = (datetime.now() - latest.timestamp).total_seconds()

            if age > self.interval * 3:
                return "Screen data is stale (capture may have stopped)."

            if latest.has_ocr and latest.ocr_text:
                # Truncate to avoid overwhelming context
                text = latest.ocr_text[:2000]
                return (
                    f"Screen ({latest.width}x{latest.height}, {age:.0f}s ago):\n{text}"
                )
            else:
                return f"Screen captured ({latest.width}x{latest.height}, {age:.0f}s ago) but no text extracted."

    def get_recent_captures(self) -> list[ScreenCapture]:
        """Get all captures in the history buffer."""
        with self._lock:
            return list(self._history)

    def detect_issues(self) -> str | None:
        """
        Analyze recent screen text for error dialogs or user struggles.
        Used by ProactiveEngine.
        """
        with self._lock:
            if not self._history:
                return None

            latest = self._history[-1]
            if not latest.has_ocr or not latest.ocr_text:
                return None

            text_lower = latest.ocr_text.lower()

            # Check for error patterns
            errors_found = [kw for kw in self._ERROR_KEYWORDS if kw in text_lower]
            if errors_found:
                return f"I noticed something on your screen that looks like an error ({', '.join(errors_found[:3])}). Need help?"

            # Check for struggle patterns (only if same pattern persists across captures)
            if len(self._history) >= 2:
                prev = self._history[-2]
                if prev.has_ocr and prev.ocr_text:
                    prev_lower = prev.ocr_text.lower()
                    struggles = [
                        kw
                        for kw in self._STRUGGLE_KEYWORDS
                        if kw in text_lower and kw in prev_lower
                    ]
                    if struggles:
                        return f"Your screen seems stuck on '{struggles[0]}'. Want me to help troubleshoot?"

        return None
