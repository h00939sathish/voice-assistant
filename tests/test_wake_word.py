"""
Tests for wake word detection functionality
"""
import pytest
import numpy as np
from unittest.mock import patch, MagicMock
from assistant.wake_word import WakeWordDetector


def test_wake_word_detector_initialization():
    """Test that WakeWordDetector initializes correctly"""
    detector = WakeWordDetector()
    assert detector is not None
    assert detector._is_loaded is False
    assert detector.use_porcupine is False
    assert detector.use_vosk is False


def test_vosk_wake_word_detection():
    """Test Vosk wake word detection"""
    detector = WakeWordDetector()

    # Simulate Vosk setup
    detector.use_vosk = True
    detector.vosk_rec = MagicMock()

    # Test with wake word
    detector.vosk_rec.AcceptWaveform.return_value = True
    detector.vosk_rec.Result.return_value = '{"text": "hey jarvis"}'

    result = detector._process_vosk(b"fake audio data")
    assert result is True


def test_openwakeword_processing():
    """Test openWakeWord processing"""
    detector = WakeWordDetector()

    # Mock the openWakeWord model
    mock_model = MagicMock()
    mock_model.predict.return_value = {}
    mock_model.prediction_buffer = {"hey_jarvis": [0.6]}  # Above threshold

    detector.oww_model = mock_model
    detector.threshold = 0.5

    # Provide properly sized audio data
    audio_data = np.array([1, 2, 3, 4], dtype=np.int16)
    result = detector._process_oww(audio_data.tobytes())
    assert result is True


def test_process_audio_without_loading():
    """Test that process_audio triggers loading when not loaded"""
    detector = WakeWordDetector()
    assert detector._is_loaded is False

    # This should return False but trigger loading in the background
    result = detector.process_audio(b"fake audio data")
    assert result is False