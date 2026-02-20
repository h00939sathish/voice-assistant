"""
Orb Overlay - Siri-like glowing orb for visual feedback
Runs in a separate process to avoid blocking the main assistant loop.
"""
import sys
import math
import logging
from multiprocessing import Process, Queue
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

# Check if PyQt6 is available
try:
    from PyQt6.QtWidgets import QApplication, QWidget, QVBoxLayout, QLabel, QFrame, QScrollArea
    from PyQt6.QtCore import Qt, QTimer, QPropertyAnimation, QEasingCurve, pyqtProperty, QPoint, QSize
    from PyQt6.QtGui import QPainter, QColor, QRadialGradient, QPen, QFont, QLinearGradient
    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    logger.warning("PyQt6 not installed. Orb overlay disabled.")


class OrbState(Enum):
    HIDDEN = "hidden"
    IDLE = "idle"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"


# Colors for each state
STATE_COLORS = {
    OrbState.HIDDEN: (0, 0, 0, 0),
    OrbState.IDLE: (100, 100, 100, 180),
    OrbState.LISTENING: (74, 144, 217, 220),    # Blue
    OrbState.PROCESSING: (255, 193, 7, 220),    # Amber
    OrbState.SPEAKING: (0, 200, 180, 220),      # Cyan/Teal
}


class MessageWidget(QFrame):
    """Modern message bubble for history panel"""
    def __init__(self, text: str, is_user: bool = True):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)
        
        # Style
        bg_color = "rgba(74, 144, 217, 40)" if is_user else "rgba(255, 255, 255, 20)"
        border_color = "rgba(74, 144, 217, 100)" if is_user else "rgba(255, 255, 255, 40)"
        text_color = "#E0E0E0"
        
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 10px;
                margin: 2px;
            }}
            QLabel {{
                background: transparent;
                border: none;
                color: {text_color};
                font-family: 'Segoe UI', sans-serif;
                font-size: 13px;
            }}
        """)
        
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)


class HistoryPanel(QWidget):
    """Glassmorphism history panel that slides out from the side"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.WindowType.FramelessWindowHint | Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        
        self.setFixedSize(300, 400)
        
        # Layout
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)
        
        # Scroll Area for messages
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setStyleSheet("background: transparent; border: none;")
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        self.container = QWidget()
        self.container.setStyleSheet("background: transparent;")
        self.container_layout = QVBoxLayout(self.container)
        self.container_layout.addStretch()
        
        self.scroll.setWidget(self.container)
        self.main_layout.addWidget(self.scroll)
        
        self._is_visible = False
        self.hide()

    def add_message(self, text: str, is_user: bool = True):
        """Add a new message bubble to history"""
        msg = MessageWidget(text, is_user)
        # Insert before the stretch
        self.container_layout.insertWidget(self.container_layout.count() - 1, msg)
        
        # Scroll to bottom
        QTimer.singleShot(100, lambda: self.scroll.verticalScrollBar().setValue(
            self.scroll.verticalScrollBar().maximum()
        ))
        
        if not self._is_visible:
            self.show_panel()

    def show_panel(self):
        self._is_visible = True
        self.show()
        self.raise_()
        # Close after 10 seconds of inactivity
        QTimer.singleShot(10000, self.hide_panel)

    def hide_panel(self):
        self._is_visible = False
        self.hide()

    def paintEvent(self, event):
        """Draw glassmorphism background"""
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Glass background
        bg_color = QColor(30, 30, 30, 180)
        painter.setBrush(bg_color)
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawRoundedRect(self.rect(), 15, 15)


if PYQT_AVAILABLE:
    class OrbWindow(QWidget):
        """Transparent window with animated glowing orb and history panel link"""
        
        def __init__(self, size: int = 120):
            super().__init__()
            self._size = size
            self._pulse = 0.0
            self._state = OrbState.HIDDEN
            self._base_color = QColor(74, 144, 217, 220)
            
            # Window setup
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint |
                Qt.WindowType.WindowStaysOnTopHint |
                Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFixedSize(size, size)
            
            # Position: bottom-right corner
            self._position_window()
            
            # History Panel
            self.history = HistoryPanel()
            self._update_history_pos()
            
            # Animation timer
            self._timer = QTimer(self)
            self._timer.timeout.connect(self._animate)
            self._timer.start(30)  # ~33 FPS
            
            self._animation_phase = 0.0
        
        def _position_window(self):
            """Position in bottom-right corner"""
            screen = QApplication.primaryScreen().geometry()
            x = screen.width() - self._size - 40
            y = screen.height() - self._size - 100
            self.move(x, y)
            if hasattr(self, 'history'):
                self._update_history_pos()

        def _update_history_pos(self):
            """Position history panel above the orb"""
            self.history.move(self.x() - 180, self.y() - 410)
        
        def add_history(self, text: str, is_user: bool):
            """Add message to history panel"""
            self.history.add_message(text, is_user)
        
        def moveEvent(self, event):
            self._update_history_pos()
            super().moveEvent(event)

        def set_state(self, state: OrbState):
            """Update orb state"""
            self._state = state
            rgba = STATE_COLORS.get(state, (100, 100, 100, 180))
            self._base_color = QColor(*rgba)
            
            if state == OrbState.HIDDEN:
                self.hide()
            else:
                self.show()
                self.raise_()
        
        def _animate(self):
            """Update animation phase"""
            self._animation_phase += 0.08
            if self._animation_phase > 2 * math.pi:
                self._animation_phase = 0
            self._pulse = (math.sin(self._animation_phase) + 1) / 2  # 0 to 1
            self.update()
        
        def paintEvent(self, event):
            """Draw the glowing orb"""
            if self._state == OrbState.HIDDEN:
                return
                
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            
            center = self._size // 2
            
            # Pulse effect: vary the radius
            base_radius = self._size // 2 - 15
            pulse_amount = 8 * self._pulse
            radius = base_radius + pulse_amount
            
            # Outer glow
            glow_color = QColor(self._base_color)
            glow_color.setAlpha(int(80 * (0.5 + 0.5 * self._pulse)))
            painter.setBrush(glow_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                int(center - radius - 10),
                int(center - radius - 10),
                int((radius + 10) * 2),
                int((radius + 10) * 2)
            )
            
            # Main orb with gradient
            gradient = QRadialGradient(center, center, radius)
            
            inner_color = QColor(self._base_color)
            inner_color.setAlpha(255)
            outer_color = QColor(self._base_color)
            outer_color.setAlpha(150)
            
            gradient.setColorAt(0, inner_color)
            gradient.setColorAt(0.7, self._base_color)
            gradient.setColorAt(1, outer_color)
            
            painter.setBrush(gradient)
            painter.setPen(QPen(QColor(255, 255, 255, 100), 2))
            painter.drawEllipse(
                int(center - radius),
                int(center - radius),
                int(radius * 2),
                int(radius * 2)
            )


def _run_orb_process(queue: Queue):
    """Entry point for the orb overlay process"""
    if not PYQT_AVAILABLE:
        logger.error("PyQt6 not available, orb process exiting")
        return
        
    app = QApplication(sys.argv)
    orb = OrbWindow()
    orb.set_state(OrbState.HIDDEN)
    
    # Check queue for state updates and history
    def check_queue():
        while not queue.empty():
            try:
                msg = queue.get_nowait()
                if msg == "quit":
                    app.quit()
                    return
                elif isinstance(msg, dict):
                    if "text" in msg:
                        orb.add_history(msg["text"], msg.get("is_user", True))
                elif msg in [s.value for s in OrbState]:
                    orb.set_state(OrbState(msg))
            except Exception:
                pass
    
    timer = QTimer()
    timer.timeout.connect(check_queue)
    timer.start(100)
    
    app.exec()


class OrbOverlay:
    """
    Controller for the orb overlay process.
    Sends state updates and history messages via multiprocessing Queue.
    """
    
    def __init__(self):
        self._queue: Optional[Queue] = None
        self._process: Optional[Process] = None
    
    def start(self):
        """Start the orb overlay in a separate process"""
        if not PYQT_AVAILABLE:
            logger.warning("Orb overlay disabled (PyQt6 not installed)")
            return
            
        self._queue = Queue()
        self._process = Process(target=_run_orb_process, args=(self._queue,), daemon=True)
        self._process.start()
        logger.info("   🔮 Orb overlay started")
    
    def set_state(self, state: str):
        """Update the orb state (hidden, listening, speaking, etc.)"""
        if self._queue:
            self._queue.put(state)
    
    def add_message(self, text: str, is_user: bool = True):
        """Add a message to the UI history panel"""
        if self._queue:
            self._queue.put({"text": text, "is_user": is_user})
    
    def show(self):
        self.set_state("idle")
    
    def hide(self):
        self.set_state("hidden")
    
    def listening(self):
        self.set_state("listening")
    
    def speaking(self):
        self.set_state("speaking")
    
    def processing(self):
        self.set_state("processing")
    
    def stop(self):
        """Stop the orb overlay process"""
        if self._queue:
            self._queue.put("quit")
        if self._process:
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()
