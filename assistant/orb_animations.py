"""
Orb Animations - Animation definitions and updates for the orb overlay.
"""

import math
from enum import Enum

if False:
    from PyQt6.QtGui import QColor


class OrbState(Enum):
    HIDDEN = "hidden"
    IDLE = "idle"
    WAKE = "wake"
    LISTENING = "listening"
    PROCESSING = "processing"
    SPEAKING = "speaking"
    SUCCESS = "success"
    ERROR = "error"


STATE_COLORS = {
    OrbState.HIDDEN: (0, 0, 0, 0),
    OrbState.IDLE: (100, 100, 100, 180),
    OrbState.WAKE: (180, 100, 255, 230),
    OrbState.LISTENING: (74, 144, 217, 220),
    OrbState.PROCESSING: (255, 193, 7, 220),
    OrbState.SPEAKING: (0, 200, 180, 220),
    OrbState.SUCCESS: (52, 199, 138, 230),
    OrbState.ERROR: (240, 80, 80, 230),
}

STATE_ANIM_SPEEDS = {
    OrbState.IDLE: 0.05,
    OrbState.WAKE: 0.18,
    OrbState.LISTENING: 0.15,
    OrbState.PROCESSING: 0.20,
    OrbState.SPEAKING: 0.10,
    OrbState.SUCCESS: 0.25,
    OrbState.ERROR: 0.30,
}


class Particle:
    __slots__ = ("x", "y", "vx", "vy", "life", "max_life", "size", "color")

    def __init__(
        self,
        x: float,
        y: float,
        vx: float,
        vy: float,
        life: float,
        size: float,
        color: "QColor",
    ):
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = life
        self.max_life = life
        self.size = size
        self.color = type(
            "QColorCopy",
            (),
            {
                "red": color.red(),
                "green": color.green(),
                "blue": color.blue(),
                "alpha": color.alpha(),
            },
        )()

    def update(self, dt: float) -> bool:
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.life -= dt
        return self.life > 0

    def alpha(self) -> float:
        return max(0.0, self.life / self.max_life)


class ParticleSystem:
    def __init__(self):
        self._particles: list[Particle] = []

    def burst(
        self,
        cx: float,
        cy: float,
        count: int,
        color: "QColor",
        speed: float = 80.0,
        upward: bool = False,
        gravity: float = 0.0,
    ):
        for i in range(count):
            angle = (2 * math.pi * i / count) + (0.3 * (i % 3) * math.pi / count)
            spd = speed * (0.7 + 0.6 * (i % 4) / 3.0)
            vx = math.cos(angle) * spd
            vy = math.sin(angle) * spd
            if upward:
                vy -= speed * 0.4
            life = 0.8 + 0.4 * (i % 3) / 2.0
            size = 3.0 + 2.0 * (i % 2)
            p = Particle(cx, cy, vx, vy + gravity, life, size, color)
            self._particles.append(p)

    def starburst(self, cx: float, cy: float, count: int, color: "QColor"):
        for i in range(count):
            angle = 2 * math.pi * i / count
            spd = 120.0 * (0.8 + 0.4 * math.sin(i * math.pi / 3))
            vx = math.cos(angle) * spd
            vy = math.sin(angle) * spd - 60
            life = 0.6 + 0.3 * math.sin(i * math.pi / 4)
            size = 4.0 + 2.0 * (i % 2)
            p = Particle(cx, cy, vx, vy, life, size, color)
            self._particles.append(p)

    def update(self, dt: float):
        self._particles = [p for p in self._particles if p.update(dt)]

    def draw(self, painter):
        for p in self._particles:
            a = int(255 * p.alpha())
            from PyQt6.QtGui import QColor

            c = QColor(p.color.red(), p.color.green(), p.color.blue())
            c.setAlpha(a)
            from PyQt6.QtCore import Qt

            painter.setBrush(c)
            painter.setPen(Qt.PenStyle.NoPen)
            r = p.size * p.alpha()
            painter.drawEllipse(int(p.x - r), int(p.y - r), int(r * 2), int(r * 2))


class OrbAnimations:
    def __init__(self):
        self._animation_phase = 0.0
        self._pulse = 0.0
        self._audio_level = 0.0
        self._smooth_audio_level = 0.0
        self._hover_glow_multiplier = 1.0
        self._target_hover_glow = 1.0

    def update(self, state: OrbState, dt: float, audio_level: float, is_hovered: bool):
        speed = STATE_ANIM_SPEEDS.get(state, 0.08)
        self._animation_phase += speed
        if self._animation_phase > 2 * math.pi:
            self._animation_phase = 0

        self._audio_level = max(0.0, min(1.0, audio_level))
        diff = self._audio_level - self._smooth_audio_level
        if diff > 0:
            self._smooth_audio_level += diff * 0.4
        else:
            self._smooth_audio_level += diff * 0.1

        self._target_hover_glow = 2.2 if is_hovered else 1.0
        glow_diff = self._target_hover_glow - self._hover_glow_multiplier
        self._hover_glow_multiplier += glow_diff * 0.15

        sine_pulse = (math.sin(self._animation_phase) + 1) / 2

        if state == OrbState.LISTENING:
            self._pulse = (sine_pulse * 0.3) + (self._smooth_audio_level * 1.5)
        elif state == OrbState.SPEAKING:
            self._pulse = 12 * sine_pulse
        elif state == OrbState.ERROR:
            self._pulse = 0.3 + 0.2 * sine_pulse
        else:
            self._pulse = sine_pulse

    def calculate_radius(
        self, state: OrbState, base_radius: int, max_radius: int
    ) -> float:
        if state == OrbState.LISTENING:
            pulse_amount = 5 + (25 * self._pulse)
        elif state == OrbState.SPEAKING:
            pulse_amount = 12 * self._pulse
        elif state == OrbState.ERROR:
            pulse_amount = 6 * self._pulse
        else:
            pulse_amount = 8 * self._pulse
        return min(base_radius + pulse_amount, max_radius)

    def get_glow_alpha(self, state: OrbState) -> int:
        glow_alpha = int(60 * (0.5 + 0.5 * self._pulse) * self._hover_glow_multiplier)
        if state == OrbState.LISTENING:
            glow_alpha = int(
                (80 + (60 * self._audio_level)) * self._hover_glow_multiplier
            )
        return glow_alpha

    @property
    def pulse(self) -> float:
        return self._pulse

    @property
    def smooth_audio_level(self) -> float:
        return self._smooth_audio_level

    @property
    def hover_glow_multiplier(self) -> float:
        return self._hover_glow_multiplier
