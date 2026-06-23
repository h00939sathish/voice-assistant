"""
Speech-to-Text using faster-whisper with Silero VAD
"""

import concurrent.futures
import gc
import logging
import os
import sys
import threading
import time
from collections.abc import Callable

import numpy as np
import torch
from faster_whisper import WhisperModel

from assistant.interfaces import IAudioManager, ISTTProvider

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    MIN_SPEECH_DURATION_MS,
    SAMPLE_RATE,
    SILENCE_DURATION_MS,
    VAD_THRESHOLD,
    WHISPER_COMPUTE_TYPE,
    WHISPER_DEVICE,
    WHISPER_MODEL,
)

logger = logging.getLogger("buddy.stt")


class SpeechToText(ISTTProvider):
    """Speech-to-Text with VAD-based endpoint detection"""

    def __init__(self):
        self.whisper_model: WhisperModel | None = None
        self.vad_model = None
        self.vad_utils = None
        self._audio_buffer: list[bytes] = []
        self._loading_lock = threading.Lock()
        self._is_loaded = False

    def load_models(self):
        """Load Whisper and VAD models (thread-safe)"""
        with self._loading_lock:
            if self._is_loaded:
                return

            logger.info("🔄 Loading STT models...")

            # 1. Load faster-whisper
            try:
                self.whisper_model = WhisperModel(
                    WHISPER_MODEL,
                    device=WHISPER_DEVICE,
                    compute_type=WHISPER_COMPUTE_TYPE,
                )
                logger.info(f"   ✅ Whisper model: {WHISPER_MODEL} ({WHISPER_DEVICE.upper()})")
            except Exception as e:
                logger.error(f"   ❌ Whisper load failed: {e}")

            # 2. Load Silero VAD (Safe Mode: pure torch)
            try:
                self.vad_model, self.vad_utils = torch.hub.load(
                    repo_or_dir="snakers4/silero-vad",
                    model="silero_vad",
                    force_reload=False,
                    onnx=False,
                )
                self.vad_model.to("cpu")
                logger.info("   ✅ Silero VAD loaded (Safe Mode)")
            except Exception as e:
                print(f"   ⚠️ Silero VAD failed ({e}). Switching to Energy Fallback.")
                self.vad_model = None  # Trigger Energy Fallback in listen logic

            self._is_loaded = True

    def unload_models(self) -> None:
        """Release STT models from RAM."""
        with self._loading_lock:
            released = False

            if self.whisper_model is not None:
                del self.whisper_model
                self.whisper_model = None
                released = True

            if self.vad_model is not None:
                del self.vad_model
                self.vad_model = None
                self.vad_utils = None
                released = True

            if released:
                self._audio_buffer = []
                self._is_loaded = False
                gc.collect()
                try:
                    torch.cuda.empty_cache()
                except Exception:
                    pass

    def reload_if_needed(self) -> None:
        """Reload Whisper if it was unloaded. No-op if already loaded."""
        if not self._is_loaded or self.whisper_model is None:
            self.load_models()

    def _check_speech(self, audio_chunk: bytes) -> float:
        """
        Check if audio chunk contains speech.
        If Silero VAD is missing, use energy-based detection.
        """
        audio_int16 = np.frombuffer(audio_chunk, dtype=np.int16)

        # 1. Try Silero VAD if available
        if self.vad_model is not None:
            try:
                audio_float = audio_int16.astype(np.float32) / 32768.0
                audio_tensor = torch.from_numpy(audio_float)
                # Ensure tensor is on correct device for the model
                speech_prob = self.vad_model(audio_tensor, SAMPLE_RATE).item()
                return speech_prob
            except Exception:
                pass  # Fall through to energy check

        # 2. Fallback: Simple RMS Energy Detection
        # Calculate Root Mean Square energy
        rms = np.sqrt(np.mean(audio_int16.astype(np.float64) ** 2))
        # Map RMS ~100-1000 to 0.0-1.0 probability
        # (Typical silence is < 50, speech is > 300)
        prob = min(1.0, max(0.0, (rms - 100) / 500))
        return prob

    def listen_with_vad(
        self,
        audio_manager: IAudioManager,
        max_duration: float = 15.0,
        audio_level_callback: Callable[[float], None] | None = None,
    ) -> bytes | None:
        """
        Listen for speech using VAD to detect when user stops speaking.

        Args:
            audio_manager: Audio manager for capturing audio
            max_duration: Maximum listening duration in seconds
            audio_level_callback: Optional callback to receive audio levels (0.0-1.0) for visualization
        """
        self.reload_if_needed()  # Transparently reload if Whisper was unloaded

        self._audio_buffer = []
        silence_samples = 0
        speech_samples = 0
        samples_per_chunk = 512  # ~32ms at 16kHz
        silence_threshold = int(
            SILENCE_DURATION_MS * SAMPLE_RATE / 1000 / samples_per_chunk
        )
        min_speech_threshold = int(
            MIN_SPEECH_DURATION_MS * SAMPLE_RATE / 1000 / samples_per_chunk
        )

        start_time = time.time()
        has_speech = False

        logger.info("👂 Listening... (speak now)")

        while time.time() - start_time < max_duration:
            chunk = audio_manager.get_audio_chunk(timeout=0.1)
            if chunk is None:
                continue

            self._audio_buffer.append(chunk)
            speech_prob = self._check_speech(chunk)

            # Calculate raw RMS energy for visualizer
            try:
                audio_int16 = np.frombuffer(chunk, dtype=np.int16)
                rms = np.sqrt(np.mean(audio_int16.astype(np.float64) ** 2))
                # Normalize: silence is usually ~50-100, normal speech is ~1000-3000
                visual_level = min(1.0, max(0.0, (rms - 100) / 2900.0))
            except Exception:
                visual_level = 0.0

            # Send audio level to callback for visualization
            if audio_level_callback:
                try:
                    audio_level_callback(visual_level)
                except Exception:
                    # Don't let visualization errors break audio capture
                    pass

            if speech_prob > VAD_THRESHOLD:
                speech_samples += 1
                silence_samples = 0
                if speech_samples >= min_speech_threshold:
                    has_speech = True
            else:
                if has_speech:
                    silence_samples += 1
                    # Check if we've had enough silence to stop
                    if silence_samples >= silence_threshold:
                        logger.info("   🔇 Silence detected, processing...")
                        break

        if not has_speech:
            logger.warning("   ⚠️ No speech detected")
            return None

        # Combine all audio chunks
        return b"".join(self._audio_buffer)

    _TRANSCRIBE_TIMEOUT = 30.0

    def transcribe(self, audio_bytes: bytes) -> tuple[str, float]:
        """
        Transcribe audio bytes to text with timeout.
        """
        if self.whisper_model is None:
            self.load_models()

        if self.whisper_model is None:
            return "Error: STT model not loaded", 0.0

        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = audio_int16.astype(np.float32) / 32768.0

        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self._transcribe_internal, audio_float)
            try:
                return future.result(timeout=self._TRANSCRIBE_TIMEOUT)
            except concurrent.futures.TimeoutError:
                print(f"   ⚠️ Transcribe timed out after {self._TRANSCRIBE_TIMEOUT}s")
                return "Error: Transcription timed out", 0.0

    def _transcribe_internal(self, audio_float: np.ndarray) -> tuple[str, float]:
        """Run whisper transcription in a separate thread."""
        segments, info = self.whisper_model.transcribe(
            audio_float,
            language=None,
            vad_filter=True,
            vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 200},
        )

        if info.language != "en":
            print(
                f"   🌍 Detected language: {info.language} ({info.language_probability:.0%})"
            )

        text_parts = []
        total_prob = 0.0
        count = 0

        for segment in segments:
            text_parts.append(segment.text)
            total_prob += segment.avg_logprob
            count += 1

        text = " ".join(text_parts).strip()
        avg_confidence = (total_prob / count) if count > 0 else -1.0
        confidence = min(1.0, max(0.0, np.exp(avg_confidence)))

        return text, confidence
