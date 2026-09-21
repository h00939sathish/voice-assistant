import math
import struct

_INTERRUPT_WINDOW_MS = 30


def rms_energy(chunk: bytes) -> float:
    if len(chunk) < 2:
        return 0.0
    count = len(chunk) // 2
    fmt = f"<{count}h"
    samples = struct.unpack(fmt, chunk[:count * 2])
    sq_sum = sum(s * s for s in samples)
    return float(math.sqrt(sq_sum / count)) / 32768.0


class InterruptionVAD:
    """Lightweight energy-based VAD for detecting when user speaks over TTS."""

    def __init__(self, threshold: float = 0.03, required_ms: int = 300, sample_rate: int = 16000):
        self.threshold = threshold
        self.required_frames = max(1, required_ms * sample_rate // 1000 // 1280)
        self._speech_frames = 0
        self._silence_frames = 0

    def reset(self):
        self._speech_frames = 0
        self._silence_frames = 0

    def is_speech(self, chunk: bytes) -> bool:
        energy = rms_energy(chunk)
        if energy > self.threshold:
            self._speech_frames += 1
            self._silence_frames = 0
        else:
            self._silence_frames += 1
            self._speech_frames = 0
        return self._speech_frames >= self.required_frames


def detect_speech_duration(
    audio_bytes: bytes,
    threshold: float = 0.03,
    sample_rate: int = 16000,
    chunk_size: int = 1280,
) -> float:
    """Analyze audio bytes and return the estimated speech duration in seconds."""
    if not audio_bytes:
        return 0.0
    chunks = [audio_bytes[i:i + chunk_size] for i in range(0, len(audio_bytes), chunk_size)]
    samples_per_chunk = chunk_size // 2
    speech_chunks = sum(1 for c in chunks if rms_energy(c) > threshold)
    return speech_chunks * samples_per_chunk / sample_rate
