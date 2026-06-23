"""
Tests for orb animations and renderer modules.
"""

import sys
from unittest.mock import MagicMock, patch

import pytest

mock_torch = MagicMock()
sys.modules["torch"] = mock_torch
mock_torch.cuda = MagicMock()
mock_torch.cuda.is_available = MagicMock(return_value=False)


class MockQColor:
    def __init__(self, r=0, g=0, b=0, a=255):
        self._r = r
        self._g = g
        self._b = b
        self._a = a

    def red(self):
        return self._r

    def green(self):
        return self._g

    def blue(self):
        return self._b

    def alpha(self):
        return self._a

    def setAlpha(self, value):
        self._a = value


class TestOrbState:
    """Tests for OrbState enum transitions."""

    def test_orb_state_all_values_defined(self):
        """Test that all expected orb states are defined."""
        from assistant.orb_animations import OrbState

        expected_states = [
            "HIDDEN",
            "IDLE",
            "WAKE",
            "LISTENING",
            "PROCESSING",
            "SPEAKING",
            "SUCCESS",
            "ERROR",
        ]
        for state_name in expected_states:
            assert hasattr(OrbState, state_name), f"Missing state: {state_name}"

    def test_orb_state_values_are_strings(self):
        """Test that all OrbState values are string types."""
        from assistant.orb_animations import OrbState

        for state in OrbState:
            assert isinstance(state.value, str)

    def test_orb_state_hidden_value(self):
        """Test HIDDEN state has correct value."""
        from assistant.orb_animations import OrbState

        assert OrbState.HIDDEN.value == "hidden"

    def test_orb_state_listening_value(self):
        """Test LISTENING state has correct value."""
        from assistant.orb_animations import OrbState

        assert OrbState.LISTENING.value == "listening"

    def test_orb_state_transition_from_hidden_to_idle(self):
        """Test valid transition from HIDDEN to IDLE."""
        from assistant.orb_animations import OrbState

        next_state = OrbState.IDLE
        assert next_state in OrbState

    def test_orb_state_transition_from_idle_to_listening(self):
        """Test valid transition from IDLE to LISTENING."""
        from assistant.orb_animations import OrbState

        next_state = OrbState.LISTENING
        assert next_state in OrbState


class TestStateColors:
    """Tests for STATE_COLORS mapping."""

    def test_state_colors_contains_all_states(self):
        """Test that STATE_COLORS contains all non-hidden states."""
        from assistant.orb_animations import STATE_COLORS, OrbState

        for state in OrbState:
            if state != OrbState.HIDDEN:
                assert state in STATE_COLORS

    def test_state_colors_alpha_values(self):
        """Test that all state colors have valid alpha values."""
        from assistant.orb_animations import STATE_COLORS

        for _state, color in STATE_COLORS.items():
            r, g, b, a = color
            assert 0 <= a <= 255

    def test_state_colors_hidden_transparent(self):
        """Test that HIDDEN state has transparent color."""
        from assistant.orb_animations import STATE_COLORS, OrbState

        r, g, b, a = STATE_COLORS[OrbState.HIDDEN]
        assert a == 0

    def test_state_colors_listening_blue_tint(self):
        """Test LISTENING state has blue tint."""
        from assistant.orb_animations import STATE_COLORS, OrbState

        r, g, b, a = STATE_COLORS[OrbState.LISTENING]
        assert b > r and b > g


class TestStateAnimSpeeds:
    """Tests for STATE_ANIM_SPEEDS mapping."""

    def test_anim_speeds_contains_all_states_except_hidden(self):
        """Test that STATE_ANIM_SPEEDS contains expected states."""
        from assistant.orb_animations import STATE_ANIM_SPEEDS, OrbState

        for state in OrbState:
            if state != OrbState.HIDDEN:
                assert state in STATE_ANIM_SPEEDS

    def test_anim_speeds_are_positive(self):
        """Test that all animation speeds are positive values."""
        from assistant.orb_animations import STATE_ANIM_SPEEDS

        for speed in STATE_ANIM_SPEEDS.values():
            assert speed > 0

    def test_anim_speeds_error_is_fastest(self):
        """Test that ERROR state has fastest animation speed."""
        from assistant.orb_animations import STATE_ANIM_SPEEDS, OrbState

        error_speed = STATE_ANIM_SPEEDS[OrbState.ERROR]
        for state, speed in STATE_ANIM_SPEEDS.items():
            if state != OrbState.ERROR:
                assert error_speed > speed


class TestParticle:
    """Tests for Particle class."""

    @pytest.fixture
    def mock_qcolor(self):
        return MockQColor(100, 150, 200, 255)

    @pytest.fixture
    def particle(self, mock_qcolor):
        from assistant.orb_animations import Particle

        return Particle(10.0, 20.0, 1.0, -0.5, 1.0, 5.0, mock_qcolor)

    def test_particle_initialization(self, particle):
        """Test particle initializes with correct values."""
        assert particle.x == 10.0
        assert particle.y == 20.0
        assert particle.vx == 1.0
        assert particle.vy == -0.5
        assert particle.life == 1.0
        assert particle.max_life == 1.0
        assert particle.size == 5.0

    def test_particle_stores_color_components(self, particle, mock_qcolor):
        """Test particle stores color RGB components."""
        assert particle.color.red == 100
        assert particle.color.green == 150
        assert particle.color.blue == 200
        assert particle.color.alpha == 255

    def test_particle_update_moves_position(self, particle):
        """Test particle update moves x and y by velocity."""
        initial_x, initial_y = particle.x, particle.y
        particle.update(0.1)
        assert particle.x != initial_x or particle.y != initial_y

    def test_particle_update_decreases_life(self, particle):
        """Test particle update decreases life."""
        initial_life = particle.life
        particle.update(0.1)
        assert particle.life < initial_life

    def test_particle_update_returns_true_when_alive(self, particle):
        """Test particle update returns True when life remains."""
        result = particle.update(0.01)
        assert result is True

    def test_particle_update_returns_false_when_dead(self, particle):
        """Test particle update returns False when life depleted."""
        result = particle.update(2.0)
        assert result is False

    def test_particle_alpha_full_life(self, particle):
        """Test alpha returns 1.0 for full life."""
        particle.life = particle.max_life
        assert particle.alpha() == 1.0

    def test_particle_alpha_half_life(self, particle):
        """Test alpha returns 0.5 for half life."""
        particle.life = particle.max_life / 2
        assert abs(particle.alpha() - 0.5) < 0.01

    def test_particle_alpha_zero_life(self, particle):
        """Test alpha returns 0.0 for zero life."""
        particle.life = 0
        assert particle.alpha() == 0.0

    def test_particle_alpha_negative_life(self, particle):
        """Test alpha clamps to 0.0 for negative life."""
        particle.life = -0.5
        assert particle.alpha() == 0.0


class TestParticleSystem:
    """Tests for ParticleSystem class."""

    @pytest.fixture
    def mock_qcolor(self):
        return MockQColor(100, 150, 200, 255)

    @pytest.fixture
    def particle_system(self):
        from assistant.orb_animations import ParticleSystem

        return ParticleSystem()

    def test_particle_system_initialization(self, particle_system):
        """Test particle system initializes empty."""
        assert particle_system._particles == []

    def test_particle_system_burst_creates_particles(
        self, particle_system, mock_qcolor
    ):
        """Test burst creates correct number of particles."""
        particle_system.burst(100, 100, 5, mock_qcolor)
        assert len(particle_system._particles) == 5

    def test_particle_system_burst_creates_count_particles(
        self, particle_system, mock_qcolor
    ):
        """Test burst creates exact count of particles."""
        particle_system.burst(100, 100, 10, mock_qcolor)
        assert len(particle_system._particles) == 10

    def test_particle_system_starburst_creates_particles(
        self, particle_system, mock_qcolor
    ):
        """Test starburst creates correct number of particles."""
        particle_system.starburst(100, 100, 8, mock_qcolor)
        assert len(particle_system._particles) == 8

    def test_particle_system_update_filters_dead_particles(
        self, particle_system, mock_qcolor
    ):
        """Test update removes dead particles."""
        particle_system.burst(100, 100, 3, mock_qcolor)
        particle_system.update(2.0)
        assert len(particle_system._particles) == 0

    def test_particle_system_update_keeps_alive_particles(
        self, particle_system, mock_qcolor
    ):
        """Test update keeps alive particles."""
        particle_system.burst(100, 100, 3, mock_qcolor)
        particle_system.update(0.01)
        assert len(particle_system._particles) == 3


class TestOrbAnimations:
    """Tests for OrbAnimations class."""

    @pytest.fixture
    def animations(self):
        from assistant.orb_animations import OrbAnimations

        return OrbAnimations()

    @pytest.fixture
    def mock_orb_state(self):
        from assistant.orb_animations import OrbState

        return OrbState

    def test_orb_animations_initialization(self, animations):
        """Test orb animations initializes with correct defaults."""
        assert animations._animation_phase == 0.0
        assert animations._pulse == 0.0
        assert animations._audio_level == 0.0
        assert animations._smooth_audio_level == 0.0
        assert animations._hover_glow_multiplier == 1.0
        assert animations._target_hover_glow == 1.0

    def test_orb_animations_update_changes_phase(self, animations, mock_orb_state):
        """Test update changes animation phase."""
        initial_phase = animations._animation_phase
        animations.update(mock_orb_state.IDLE, 0.1, 0.0, False)
        assert animations._animation_phase != initial_phase

    def test_orb_animations_update_audio_level(self, animations, mock_orb_state):
        """Test update processes audio level."""
        animations.update(mock_orb_state.LISTENING, 0.1, 0.8, False)
        assert animations._audio_level == 0.8

    def test_orb_animations_audio_level_clamped(self, animations, mock_orb_state):
        """Test audio level is clamped to 0-1 range."""
        animations.update(mock_orb_state.LISTENING, 0.1, 1.5, False)
        assert animations._audio_level == 1.0

    def test_orb_animations_smooth_audio_level_smoothing(
        self, animations, mock_orb_state
    ):
        """Test smooth audio level applies smoothing."""
        animations.update(mock_orb_state.LISTENING, 0.1, 0.5, False)
        assert animations._smooth_audio_level != animations._audio_level

    def test_orb_animations_hover_glow_multiplier(self, animations, mock_orb_state):
        """Test hover glow multiplier changes on hover."""
        animations.update(mock_orb_state.IDLE, 0.1, 0.0, True)
        assert animations._hover_glow_multiplier > 1.0

    def test_orb_animations_pulse_idle_state(self, animations, mock_orb_state):
        """Test pulse calculation for IDLE state."""
        animations.update(mock_orb_state.IDLE, 0.1, 0.0, False)
        assert 0.0 <= animations._pulse <= 1.0

    def test_orb_animations_pulse_listening_with_audio(
        self, animations, mock_orb_state
    ):
        """Test pulse for LISTENING state with audio."""
        animations.update(mock_orb_state.LISTENING, 0.1, 0.5, False)
        assert animations._pulse > 0.3

    def test_orb_animations_pulse_speaking_state(self, animations, mock_orb_state):
        """Test pulse calculation for SPEAKING state."""
        animations.update(mock_orb_state.SPEAKING, 0.1, 0.0, False)
        assert 0.0 <= animations._pulse <= 12.0

    def test_orb_animations_pulse_error_state(self, animations, mock_orb_state):
        """Test pulse calculation for ERROR state."""
        animations.update(mock_orb_state.ERROR, 0.1, 0.0, False)
        assert 0.3 <= animations._pulse <= 0.5

    def test_calculate_radius_idle_state(self, animations, mock_orb_state):
        """Test radius calculation for IDLE state."""
        radius = animations.calculate_radius(mock_orb_state.IDLE, 60, 100)
        assert radius >= 60
        assert radius <= 100

    def test_calculate_radius_listening_state(self, animations, mock_orb_state):
        """Test radius calculation for LISTENING state."""
        animations._pulse = 0.5
        radius = animations.calculate_radius(mock_orb_state.LISTENING, 60, 100)
        assert radius > 60

    def test_calculate_radius_speaking_state(self, animations, mock_orb_state):
        """Test radius calculation for SPEAKING state."""
        animations._pulse = 0.5
        radius = animations.calculate_radius(mock_orb_state.SPEAKING, 60, 100)
        assert radius > 60

    def test_calculate_radius_respects_max(self, animations, mock_orb_state):
        """Test radius respects max_radius limit."""
        animations._pulse = 10.0
        radius = animations.calculate_radius(mock_orb_state.IDLE, 60, 80)
        assert radius <= 80

    def test_get_glow_alpha_idle_state(self, animations, mock_orb_state):
        """Test glow alpha for IDLE state."""
        animations._pulse = 0.5
        animations._hover_glow_multiplier = 1.0
        alpha = animations.get_glow_alpha(mock_orb_state.IDLE)
        assert 0 <= alpha <= 120

    def test_get_glow_alpha_listening_state(self, animations, mock_orb_state):
        """Test glow alpha for LISTENING state with audio."""
        animations._audio_level = 0.5
        animations._hover_glow_multiplier = 1.0
        alpha = animations.get_glow_alpha(mock_orb_state.LISTENING)
        assert alpha > 80

    def test_get_glow_alpha_increases_with_hover(self, animations, mock_orb_state):
        """Test glow alpha increases on hover."""
        animations._pulse = 0.5
        alpha_no_hover = animations.get_glow_alpha(mock_orb_state.IDLE)
        animations._hover_glow_multiplier = 2.2
        alpha_hover = animations.get_glow_alpha(mock_orb_state.IDLE)
        assert alpha_hover > alpha_no_hover

    def test_orb_animations_pulse_property(self, animations, mock_orb_state):
        """Test pulse property returns correct value."""
        animations.update(mock_orb_state.IDLE, 0.1, 0.0, False)
        assert animations.pulse == animations._pulse

    def test_orb_animations_smooth_audio_level_property(
        self, animations, mock_orb_state
    ):
        """Test smooth_audio_level property returns correct value."""
        animations.update(mock_orb_state.IDLE, 0.1, 0.5, False)
        assert animations.smooth_audio_level == animations._smooth_audio_level

    def test_orb_animations_hover_glow_multiplier_property(
        self, animations, mock_orb_state
    ):
        """Test hover_glow_multiplier property returns correct value."""
        animations.update(mock_orb_state.IDLE, 0.1, 0.0, True)
        assert animations.hover_glow_multiplier == animations._hover_glow_multiplier


class TestOrbAnimationsStateTransitions:
    """Tests for OrbAnimations state-specific behavior."""

    @pytest.fixture
    def animations(self):
        from assistant.orb_animations import OrbAnimations

        return OrbAnimations()

    @pytest.fixture
    def mock_orb_state(self):
        from assistant.orb_animations import OrbState

        return OrbState

    def test_transition_hidden_to_idle(self, animations, mock_orb_state):
        """Test transition handling from HIDDEN to IDLE."""
        animations.update(mock_orb_state.IDLE, 0.1, 0.0, False)
        assert animations._pulse >= 0.0

    def test_transition_idle_to_listening(self, animations, mock_orb_state):
        """Test transition from IDLE to LISTENING."""
        animations.update(mock_orb_state.IDLE, 0.1, 0.0, False)
        animations.update(mock_orb_state.LISTENING, 0.1, 0.5, False)
        assert animations._audio_level == 0.5

    def test_transition_listening_to_processing(self, animations, mock_orb_state):
        """Test transition from LISTENING to PROCESSING."""
        animations.update(mock_orb_state.LISTENING, 0.1, 0.0, False)
        animations.update(mock_orb_state.PROCESSING, 0.1, 0.0, False)
        assert animations._pulse >= 0.0

    def test_transition_processing_to_speaking(self, animations, mock_orb_state):
        """Test transition from PROCESSING to SPEAKING."""
        animations.update(mock_orb_state.PROCESSING, 0.1, 0.0, False)
        animations.update(mock_orb_state.SPEAKING, 0.1, 0.0, False)
        assert animations._pulse >= 0.0

    def test_transition_to_success(self, animations, mock_orb_state):
        """Test transition to SUCCESS state."""
        animations.update(mock_orb_state.SUCCESS, 0.1, 0.0, False)
        assert animations._pulse >= 0.0

    def test_transition_to_error(self, animations, mock_orb_state):
        """Test transition to ERROR state."""
        animations.update(mock_orb_state.ERROR, 0.1, 0.0, False)
        assert 0.3 <= animations._pulse <= 0.5


class TestOrbRenderer:
    """Tests for OrbRenderer class."""

    @pytest.fixture
    def mock_qcolor(self):
        return MockQColor(100, 150, 200, 255)

    @pytest.fixture
    def orb_renderer(self, mock_qcolor):
        with patch.dict(
            "sys.modules",
            {
                "PyQt6": MagicMock(),
                "PyQt6.QtWidgets": MagicMock(),
                "PyQt6.QtCore": MagicMock(),
                "PyQt6.QtGui": MagicMock(),
            },
        ):
            from assistant.orb_renderer import OrbRenderer

            return OrbRenderer(200, mock_qcolor)

    def test_orb_renderer_size_property(self, orb_renderer):
        """Test size property returns correct value."""
        assert orb_renderer.size == 200

    def test_orb_renderer_base_color_property(self, orb_renderer, mock_qcolor):
        """Test base_color property returns correct value."""
        assert orb_renderer.base_color == mock_qcolor

    def test_orb_renderer_base_color_setter(self, orb_renderer, mock_qcolor):
        """Test base_color setter updates value."""
        new_color = MockQColor(50, 50, 50, 255)
        orb_renderer.base_color = new_color
        assert orb_renderer.base_color == new_color
