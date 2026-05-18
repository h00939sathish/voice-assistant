"""
Orb Renderer - Rendering and drawing logic for the orb overlay.
"""

try:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import (
        QBrush,
        QColor,
        QPainter,
        QPainterPath,
        QPen,
        QRadialGradient,
    )
    from PyQt6.QtWidgets import QApplication

    PYQT_AVAILABLE = True
except ImportError:
    PYQT_AVAILABLE = False


class OrbRenderer:
    def __init__(self, size: int, base_color: QColor):
        self._size = size
        self._base_color = base_color

    @property
    def size(self) -> int:
        return self._size

    @property
    def base_color(self) -> QColor:
        return self._base_color

    @base_color.setter
    def base_color(self, value: QColor):
        self._base_color = value

    def draw_orb(self, painter: QPainter, state, animations, is_hovered: bool):
        if state.value == "hidden":
            return

        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setClipRect(painter.viewport())

        center = self._size // 2
        base_radius = 60

        radius = animations.calculate_radius(state, base_radius, (self._size // 2) - 40)
        self._draw_particles(painter, state)

        glow_alpha = animations.get_glow_alpha(state)
        self._draw_glow_rings(painter, center, radius, glow_alpha, state)

        if is_hovered:
            self._draw_hover_rim(
                painter, center, radius, animations.hover_glow_multiplier
            )

        if state.value == "listening" and animations.smooth_audio_level > 0.05:
            self._draw_spectrum_bars(
                painter, center, radius, animations.smooth_audio_level, state
            )

        self._draw_main_orb(painter, center, radius, state)
        self._draw_inner_highlight(painter, center, radius)

    def _draw_particles(self, painter, state):
        pass

    def _draw_glow_rings(
        self, painter: QPainter, center: int, radius: float, glow_alpha: int, state
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

    def _draw_hover_rim(
        self, painter: QPainter, center: int, radius: float, glow_multiplier: float
    ):
        rim_color = QColor(255, 255, 255, int(60 * glow_multiplier))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(QPen(rim_color, 2))
        painter.drawEllipse(
            int(center - radius - 5),
            int(center - radius - 5),
            int((radius + 5) * 2),
            int((radius + 5) * 2),
        )

    def _draw_spectrum_bars(
        self, painter: QPainter, center: int, radius: int, audio_level: float, state
    ):

        bar_count = 8
        bar_width = (radius * 1.2) / bar_count
        max_bar_height = radius * 0.8
        start_x = center - (radius * 0.6)

        for i in range(bar_count):
            height_factor = audio_level * (0.3 + 0.7 * (i % 3 + 1) / 3)
            height = max(2, max_bar_height * height_factor)
            x = start_x + i * bar_width
            y = center + radius * 0.2 - height

            bar_color = QColor(self._base_color)
            bar_color.setAlpha(180)
            painter.setBrush(bar_color)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRect(int(x), int(y), int(bar_width - 2), int(height))

    def _draw_main_orb(self, painter: QPainter, center: int, radius: float, state):
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
            int(center - radius), int(center - radius), int(radius * 2), int(radius * 2)
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

    def draw_snap_hint(self, painter: QPainter):
        if not PYQT_AVAILABLE:
            return
        screen = QApplication.primaryScreen().geometry()
        margin = 30
        current_pos = self._last_pos if hasattr(self, "_last_pos") else None
        if current_pos is None:
            return

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

    def set_last_pos(self, pos):
        self._last_pos = pos
