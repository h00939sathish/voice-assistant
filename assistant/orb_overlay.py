"""
Orb Overlay - Siri-like glowing orb for visual feedback
Runs in a separate process to avoid blocking the main assistant loop.

Refactored to separate modules:
- orb_animations.py: Animation definitions and updates
- orb_renderer.py: Rendering and drawing logic
"""

import json
import logging
import sys
from multiprocessing import Process, Queue
from pathlib import Path

logger = logging.getLogger(__name__)

try:
    from PyQt6.QtCore import (
        QPoint,
        Qt,
        QTimer,
    )
    from PyQt6.QtGui import (
        QColor,
        QPainter,
        QPen,
        QRadialGradient,
    )
    from PyQt6.QtWidgets import (
        QApplication,
        QFrame,
        QLabel,
        QScrollArea,
        QSizePolicy,
        QVBoxLayout,
        QWidget,
    )

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False
    logger.warning("PyQt6 not installed. Orb overlay disabled.")

from assistant.orb_animations import (
    STATE_COLORS,
    OrbState,
    ParticleSystem,
)


class MessageWidget(QFrame):
    """Modern message bubble for history panel."""

    def __init__(self, text: str, is_user: bool = True):
        super().__init__()
        self.setFrameShape(QFrame.Shape.StyledPanel)
        layout = QVBoxLayout(self)

        bg_color = "rgba(74, 144, 217, 40)" if is_user else "rgba(255, 255, 255, 20)"
        border_color = (
            "rgba(74, 144, 217, 100)" if is_user else "rgba(255, 255, 255, 40)"
        )
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
    """Glassmorphism history panel that slides out from the side."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.Tool
            | Qt.WindowType.WindowStaysOnTopHint
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(300, 400)

        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(10, 10, 10, 10)

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
        self._auto_hide_timer = QTimer()
        self._auto_hide_timer.timeout.connect(self._auto_hide)
        self.hide()

    def add_message(self, text: str, is_user: bool = True):
        msg = MessageWidget(text, is_user)
        self.container_layout.insertWidget(self.container_layout.count() - 1, msg)
        QTimer.singleShot(
            100,
            lambda: self.scroll.verticalScrollBar().setValue(
                self.scroll.verticalScrollBar().maximum()
            ),
        )
        if not self._is_visible:
            self.show_panel()

    def show_panel(self, auto_hide_ms: int = 10000):
        self._is_visible = True
        self._auto_hide_timer.stop()
        self.show()
        self.raise_()
        if auto_hide_ms > 0:
            self._auto_hide_timer.start(auto_hide_ms)

    def hide_panel(self):
        self._is_visible = False
        self._auto_hide_timer.stop()
        self.hide()

    def toggle(self):
        if self._is_visible:
            self.hide_panel()
        else:
            self.show_panel()

    def _auto_hide(self):
        if self._is_visible:
            self.hide_panel()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        bg_color = QColor(30, 30, 30, 180)
        painter.setBrush(bg_color)
        painter.setPen(QPen(QColor(255, 255, 255, 40), 1))
        painter.drawRoundedRect(self.rect(), 15, 15)


class TranscriptionWidget(QLabel):
    """Floating text that appears below the orb with character-by-character typing animation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setFixedWidth(350)
        self._full_text = ""
        self._typed_chars = 0
        self._is_partial = False
        self._hide_timer = QTimer()
        self._hide_timer.timeout.connect(self.hide)
        self._type_timer = QTimer()
        self._type_timer.timeout.connect(self._advance_char)
        self._type_speed_ms = 30
        self.hide()

    def set_text(self, text: str, is_partial: bool = False):
        self._is_partial = is_partial
        self._hide_timer.stop()
        self._type_timer.stop()

        if is_partial:
            self._full_text = ""
            self._typed_chars = 0
            self.setText(text)
            self._apply_style(is_partial)
            self.show()
            self.raise_()
        else:
            self._full_text = text
            self._typed_chars = 0
            self._apply_style(is_partial)
            self.show()
            self.raise_()
            self._type_timer.start(self._type_speed_ms)

    def _advance_char(self):
        if self._typed_chars < len(self._full_text):
            self._typed_chars += 1
            self.setText(self._full_text[: self._typed_chars])
        else:
            self._type_timer.stop()
            self._hide_timer.start(4000)

    def _apply_style(self, is_partial: bool):
        bg_opacity = "100" if is_partial else "180"
        text_color = "#AAAAAA" if is_partial else "#FFFFFF"
        self.setStyleSheet(f"""
            QLabel {{
                color: {text_color};
                font-size: 15px;
                font-family: 'Segoe UI', sans-serif;
                background: rgba(0, 0, 0, {bg_opacity});
                padding: 12px 20px;
                border-radius: 20px;
                border: 1px solid rgba(255, 255, 255, {"30" if is_partial else "60"});
            }}
        """)
        self.adjustSize()

    def position_below(self, orb_x: int, orb_y: int, orb_size: int):
        x = orb_x + (orb_size - self.width()) // 2
        y = orb_y + orb_size + 10
        self.move(x, y)


if PYQT_AVAILABLE:

    class FullScreenOverlay(QWidget):
        """Full screen transparent black overlay that fades in/out."""

        def __init__(self):
            super().__init__()
            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
                | Qt.WindowType.WindowTransparentForInput
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            screen = QApplication.primaryScreen().geometry()
            self.setGeometry(screen)
            self.setStyleSheet("background-color: transparent;")
            self._target_opacity = 0.0
            self._current_opacity = 0.0
            self._animation_timer = QTimer(self)
            self._animation_timer.timeout.connect(self._animate_opacity)
            self._animation_timer.start(16)
            self.hide()

        def set_target_opacity(self, opacity: float):
            self._target_opacity = opacity
            if opacity > 0:
                self.show()

        def _animate_opacity(self):
            diff = self._target_opacity - self._current_opacity
            if abs(diff) > 0.01:
                self._current_opacity += diff * 0.1
                self.update()
            elif self._target_opacity == 0.0 and self._current_opacity < 0.01:
                self._current_opacity = 0.0
                self.hide()

        def paintEvent(self, event):
            if self._current_opacity <= 0:
                return
            painter = QPainter(self)
            painter.setOpacity(self._current_opacity)
            painter.fillRect(self.rect(), QColor(0, 0, 0, 160))

    from assistant.orb_animations import OrbAnimations

    class OrbWindow(QWidget):
        """Transparent window with animated glowing orb."""

        def __init__(self, size: int = 200):
            super().__init__()
            self._size = size
            self._state = OrbState.HIDDEN
            self._base_color = QColor(74, 144, 217, 220)
            self._audio_level = 0.0

            self._is_hovered = False
            self._shake_offset = 0
            self._shake_timer = QTimer()
            self._shake_timer.timeout.connect(self._update_shake)

            self._show_snap_hint = False
            self._snap_hint_timer = QTimer()
            self._snap_hint_timer.timeout.connect(
                lambda: setattr(self, "_show_snap_hint", False)
            )

            self._particles = ParticleSystem()
            self._animations = OrbAnimations()

            self._drag_start = QPoint()
            self._dragging = False

            self._pos_file = str(Path.home() / ".buddy_orb_position.json")
            self._loaded_pos = self._load_position()

            self.setWindowFlags(
                Qt.WindowType.FramelessWindowHint
                | Qt.WindowType.WindowStaysOnTopHint
                | Qt.WindowType.Tool
            )
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setFixedSize(size, size)
            self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
            self.setMouseTracking(True)

            self._position_window()
            self.history = HistoryPanel()
            self._update_history_pos()

            self.transcription = TranscriptionWidget()

            self._timer = QTimer(self)
            self._timer.timeout.connect(self._animate)
            self._timer.start(16)

            self._last_dt = 0.016
            self._prev_state = self._state

        def _load_position(self) -> tuple[int, int] | None:
            try:
                with open(self._pos_file) as f:
                    data = json.load(f)
                    return data.get("x"), data.get("y")
            except Exception:
                return None

        def _save_position(self):
            try:
                with open(self._pos_file, "w") as f:
                    json.dump({"x": self.x(), "y": self.y()}, f)
            except Exception:
                pass

        def _position_window(self):
            screen = QApplication.primaryScreen().geometry()
            if self._loaded_pos:
                x, y = self._loaded_pos
                x = max(0, min(x, screen.width() - self._size))
                y = max(0, min(y, screen.height() - self._size))
            else:
                x = screen.width() - self._size + 10
                y = screen.height() - self._size - 50
            self.move(x, y)
            if hasattr(self, "history"):
                self._update_history_pos()
            if hasattr(self, "transcription"):
                self._update_transcription_pos()

        def _update_history_pos(self):
            if hasattr(self, "history"):
                self.history.move(self.x() - 180, self.y() - 410)

        def _update_transcription_pos(self):
            if hasattr(self, "transcription"):
                self.transcription.position_below(self.x(), self.y() - 50, self._size)

        def add_history(self, text: str, is_user: bool):
            self.history.add_message(text, is_user)

        def set_transcription(self, text: str, is_partial: bool = False):
            self.transcription.set_text(text, is_partial)
            self._update_transcription_pos()

        def set_audio_level(self, level: float):
            self._audio_level = max(0.0, min(1.0, level))

        def history_toggle(self):
            self.history.toggle()

        def mousePressEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                self._drag_start = event.globalPosition().toPoint() - self.pos()
                self._dragging = False
                self._show_snap_hint = False
                self._snap_hint_timer.stop()
                event.accept()
            elif event.button() == Qt.MouseButton.RightButton:
                self.history_toggle()
                event.accept()

        def mouseMoveEvent(self, event):
            if event.buttons() & Qt.MouseButton.LeftButton:
                delta = event.globalPosition().toPoint() - self._drag_start
                if not self._dragging and (delta - self.pos()).manhattanLength() > 5:
                    self._dragging = True
                if self._dragging:
                    self.move(delta)
                    self._check_snap_hint(event.globalPosition().toPoint())
                    self._update_history_pos()
                    self._update_transcription_pos()
                    self._show_snap_hint = True
                    self.update()
            super().mouseMoveEvent(event)

        def mouseReleaseEvent(self, event):
            if event.button() == Qt.MouseButton.LeftButton:
                if self._dragging:
                    self._save_position()
                    self._dragging = False
                    self._show_snap_hint = False
                    self.update()
                self._drag_start = QPoint()
            super().mouseReleaseEvent(event)

        def _check_snap_hint(self, global_pos: QPoint):
            screen = QApplication.primaryScreen().geometry()
            margin = 30
            for _corner_name, cx, cy in [
                ("top-left", 0, 0),
                ("top-right", screen.width(), 0),
                ("bottom-left", 0, screen.height()),
                ("bottom-right", screen.width(), screen.height()),
            ]:
                if (
                    abs(global_pos.x() - cx) < margin
                    and abs(global_pos.y() - cy) < margin
                ):
                    self._show_snap_hint = True
                    return

        def enterEvent(self, event):
            self._is_hovered = True
            super().enterEvent(event)

        def leaveEvent(self, event):
            self._is_hovered = False
            super().leaveEvent(event)

        def _update_shake(self):
            import random

            self._shake_offset = random.uniform(-4, 4)
            self.update()

        def moveEvent(self, event):
            self._update_history_pos()
            self._update_transcription_pos()
            super().moveEvent(event)

        def set_state(self, state: OrbState):
            old_state = self._state
            self._state = state

            rgba = STATE_COLORS.get(state, (100, 100, 100, 180))
            self._base_color = QColor(*rgba)

            if state == OrbState.HIDDEN:
                self.hide()
                self.transcription.hide()
                self.history.hide_panel()
                self._shake_timer.stop()
                return

            if state == OrbState.ERROR:
                self._shake_timer.start(50)

            if state == OrbState.SUCCESS:
                cx = self._size // 2
                cy = self._size // 2
                self._particles.starburst(
                    cx, cy, 12, QColor(*STATE_COLORS[OrbState.SUCCESS])
                )
                QTimer.singleShot(2000, lambda: self.set_state(OrbState.IDLE))

            if old_state != state:
                cx = self._size // 2
                cy = self._size // 2
                if state == OrbState.LISTENING:
                    self._particles.burst(
                        cx,
                        cy,
                        8,
                        QColor(*STATE_COLORS[OrbState.LISTENING]),
                        speed=60,
                        upward=True,
                    )
                elif state == OrbState.SPEAKING:
                    self._particles.burst(
                        cx,
                        cy,
                        6,
                        QColor(*STATE_COLORS[OrbState.SPEAKING]),
                        speed=40,
                        upward=True,
                        gravity=20,
                    )
                elif state == OrbState.WAKE:
                    self._particles.burst(
                        cx,
                        cy,
                        10,
                        QColor(*STATE_COLORS[OrbState.WAKE]),
                        speed=70,
                        upward=False,
                    )
                elif state == OrbState.PROCESSING:
                    self._particles.burst(
                        cx, cy, 5, QColor(*STATE_COLORS[OrbState.PROCESSING]), speed=50
                    )

            self._prev_state = old_state
            self.show()
            self.raise_()
            self._update_transcription_pos()

        def _animate(self):
            dt = self._last_dt
            self._animations.update(
                self._state, dt, self._audio_level, self._is_hovered
            )
            self._particles.update(dt)
            self.update()

        def paintEvent(self, event):
            if self._state == OrbState.HIDDEN:
                return

            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            painter.setClipRect(self.rect())

            if self._state == OrbState.ERROR:
                painter.save()
                painter.translate(self._shake_offset, 0)

            center = self._size // 2
            base_radius = 60
            max_radius = (self._size // 2) - 40

            radius = self._animations.calculate_radius(
                self._state, base_radius, max_radius
            )

            self._particles.draw(painter)

            glow_alpha = self._animations.get_glow_alpha(self._state)
            self._draw_glow_rings(painter, center, radius, glow_alpha)

            if self._is_hovered:
                self._draw_hover_rim(painter, center, radius)

            if (
                self._state == OrbState.LISTENING
                and self._animations.smooth_audio_level > 0.05
            ):
                self._draw_spectrum_bars(painter, center, radius)

            self._draw_main_orb(painter, center, radius)
            self._draw_inner_highlight(painter, center, radius)

            if self._show_snap_hint:
                self._draw_snap_hint(painter)

            if self._state == OrbState.ERROR:
                painter.restore()

        def _draw_glow_rings(
            self, painter: QPainter, center: int, radius: float, glow_alpha: int
        ):
            glow_color = QColor(self._base_color)
            glow_color.setAlpha(glow_alpha)

            for i, glow_radius in enumerate([radius + 15, radius + 25, radius + 35]):
                alpha = int(glow_alpha * (1 - i * 0.25))
                glow_color.setAlpha(max(0, alpha))
                painter.setBrush(glow_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawEllipse(
                    int(center - glow_radius),
                    int(center - glow_radius),
                    int(glow_radius * 2),
                    int(glow_radius * 2),
                )

        def _draw_hover_rim(self, painter: QPainter, center: int, radius: float):
            rim_color = QColor(
                255, 255, 255, int(60 * self._animations.hover_glow_multiplier)
            )
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(rim_color, 2))
            painter.drawEllipse(
                int(center - radius - 5),
                int(center - radius - 5),
                int((radius + 5) * 2),
                int((radius + 5) * 2),
            )

        def _draw_spectrum_bars(self, painter: QPainter, center: int, radius: int):
            bar_count = 8
            bar_width = (radius * 1.2) / bar_count
            max_bar_height = radius * 0.8
            start_x = center - (radius * 0.6)

            for i in range(bar_count):
                height_factor = self._animations.smooth_audio_level * (
                    0.3 + 0.7 * (i % 3 + 1) / 3
                )
                height = max(2, max_bar_height * height_factor)
                x = start_x + i * bar_width
                y = center + radius * 0.2 - height

                bar_color = QColor(self._base_color)
                bar_color.setAlpha(180)
                painter.setBrush(bar_color)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.drawRect(int(x), int(y), int(bar_width - 2), int(height))

        def _draw_main_orb(self, painter: QPainter, center: int, radius: float):
            gradient = QRadialGradient(center, center, int(radius))
            inner_color = QColor(self._base_color)
            inner_color.setAlpha(255)
            mid_color = QColor(self._base_color)
            mid_color.setAlpha(200)
            outer_color = QColor(self._base_color)
            outer_color.setAlpha(120)

            gradient.setColorAt(0, inner_color)
            gradient.setColorAt(0.5, mid_color)
            gradient.setColorAt(1, outer_color)

            painter.setBrush(gradient)
            border_color = QColor(255, 255, 255, 150)
            painter.setPen(QPen(border_color, 2))
            painter.drawEllipse(
                int(center - radius),
                int(center - radius),
                int(radius * 2),
                int(radius * 2),
            )

        def _draw_inner_highlight(self, painter: QPainter, center: int, radius: float):
            highlight_radius = radius * 0.4
            highlight = QRadialGradient(
                int(center - radius * 0.2),
                int(center - radius * 0.2),
                int(highlight_radius),
            )
            highlight.setColorAt(0, QColor(255, 255, 255, 80))
            highlight.setColorAt(1, QColor(255, 255, 255, 0))
            painter.setBrush(highlight)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(
                int(center - radius * 0.2 - highlight_radius),
                int(center - radius * 0.2 - highlight_radius),
                int(highlight_radius * 2),
                int(highlight_radius * 2),
            )

        def _draw_snap_hint(self, painter: QPainter):
            screen = QApplication.primaryScreen().geometry()
            margin = 30
            current_pos = self.pos()
            hw, hh = self._size // 2, self._size // 2

            for _name, cx, cy in [
                ("TL", 0, 0),
                ("TR", screen.width(), 0),
                ("BL", 0, screen.height()),
                ("BR", screen.width(), screen.height()),
            ]:
                dx = abs(current_pos.x() + hw - cx)
                dy = abs(current_pos.y() + hh - cy)
                if dx < margin and dy < margin:
                    hint_color = QColor(255, 255, 255, 100)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.setPen(QPen(hint_color, 2))
                    r = 8
                    painter.drawEllipse(cx - r, cy - r, r * 2, r * 2)


def _run_orb_process(queue: Queue):
    """Entry point for the orb overlay process."""
    if not PYQT_AVAILABLE:
        logger.error("PyQt6 not available, orb process exiting")
        return

    app = QApplication(sys.argv)
    app.setApplicationName("BuddyOrb")
    orb = OrbWindow(size=200)
    orb.set_state(OrbState.HIDDEN)

    def check_queue():
        max_batch = 20
        processed = 0
        while not queue.empty() and processed < max_batch:
            try:
                msg = queue.get_nowait()
                if msg == "quit":
                    app.quit()
                    return
                elif isinstance(msg, dict):
                    if "text" in msg:
                        orb.add_history(msg["text"], msg.get("is_user", True))
                    elif "transcription" in msg:
                        orb.set_transcription(
                            msg["transcription"], msg.get("is_partial", False)
                        )
                    elif "audio_level" in msg:
                        orb.set_audio_level(msg["audio_level"])
                    elif "action" in msg and msg["action"] == "toggle_history":
                        orb.history_toggle()
                elif isinstance(msg, float):
                    orb.set_audio_level(msg)
                elif msg in [s.value for s in OrbState]:
                    orb.set_state(OrbState(msg))
                processed += 1
            except Exception as e:
                logger.debug(f"Queue processing error: {e}")
                break

    timer = QTimer()
    timer.timeout.connect(check_queue)
    timer.start(16)

    app.exec()


class OrbOverlay:
    """Controller for the orb overlay process."""

    def __init__(self):
        self._queue: Queue | None = None
        self._process: Process | None = None

    def start(self):
        if not PYQT_AVAILABLE:
            logger.warning("Orb overlay disabled (PyQt6 not installed)")
            return

        self._queue = Queue()
        self._process = Process(
            target=_run_orb_process, args=(self._queue,), daemon=True
        )
        self._process.start()
        logger.info("   Orb overlay started")

    def set_state(self, state: str):
        if self._queue:
            try:
                self._queue.put_nowait(state)
            except Exception:
                pass

    def add_message(self, text: str, is_user: bool = True):
        if self._queue:
            try:
                self._queue.put_nowait({"text": text, "is_user": is_user})
            except Exception:
                pass

    def set_transcription(self, text: str, is_partial: bool = False):
        if self._queue:
            try:
                self._queue.put_nowait(
                    {"transcription": text, "is_partial": is_partial}
                )
            except Exception:
                pass

    def set_audio_level(self, level: float):
        if self._queue:
            try:
                self._queue.put_nowait({"audio_level": float(level)})
            except Exception:
                pass

    def toggle_history(self):
        if self._queue:
            try:
                self._queue.put_nowait({"action": "toggle_history"})
            except Exception:
                pass

    def show(self):
        self.set_state("idle")

    def hide(self):
        self.set_state("hidden")

    def wake(self):
        self.set_state("wake")

    def listening(self):
        self.set_state("listening")

    def speaking(self):
        self.set_state("speaking")

    def processing(self):
        self.set_state("processing")

    def success(self):
        self.set_state("success")

    def error(self):
        self.set_state("error")

    def stop(self):
        if self._queue:
            self._queue.put("quit")
        if self._process:
            self._process.join(timeout=1.0)
            if self._process.is_alive():
                self._process.terminate()
