"""
Audio Manager - Handles microphone input and speaker output
"""

import logging
import os
import queue
import sys
import time
from collections.abc import Generator

import numpy as np
import sounddevice as sd

from assistant.interfaces import IAudioManager

# Add parent to path for config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AUDIO_INPUT_DEVICE, CHANNELS, CHUNK_SIZE, SAMPLE_RATE

logger = logging.getLogger("buddy.audio")


class AudioManager(IAudioManager):
    """Manages audio input/output streams"""

    def __init__(self):
        self.sample_rate = SAMPLE_RATE
        self.channels = CHANNELS
        self.chunk_size = CHUNK_SIZE
        self.device_config = (AUDIO_INPUT_DEVICE or "auto").strip()
        self.auto_input_device = self.device_config.lower() in {"", "auto", "default"}
        self.input_device = self._resolve_input_device(self.device_config)
        self._active_input_device = self.input_device
        self._last_device_check = 0.0
        self._device_check_interval = 2.0
        self.audio_queue: queue.Queue = queue.Queue(
            maxsize=0
        )  # Unlimited maxsize, we manage limit manually
        self.is_recording = False
        self._stream: sd.InputStream | None = None
        self._verify_audio_device()

    def _resolve_input_device(self, configured_device: str) -> int | None:
        """Resolve configured input device by numeric index or case-insensitive name match."""
        configured_device = (configured_device or "auto").strip()
        if configured_device.lower() in {"", "auto", "default"}:
            return self._current_default_input_device()

        devices = sd.query_devices()
        if configured_device.isdigit():
            device_index = int(configured_device)
            if device_index >= len(devices):
                raise RuntimeError(
                    f"Configured AUDIO_INPUT_DEVICE index {device_index} does not exist"
                )
            if devices[device_index]["max_input_channels"] <= 0:
                raise RuntimeError(
                    f"Configured AUDIO_INPUT_DEVICE {device_index} is not an input device"
                )
            return device_index

        needle = configured_device.lower()
        matches = [
            index
            for index, device in enumerate(devices)
            if device["max_input_channels"] > 0
            and needle in str(device["name"]).lower()
        ]
        if not matches:
            raise RuntimeError(
                f"No input device matches AUDIO_INPUT_DEVICE='{configured_device}'"
            )
        return matches[0]

    def _current_default_input_device(self) -> int | None:
        """Return the current default input device index, if sounddevice exposes one."""
        default_device = sd.default.device
        if isinstance(default_device, (list, tuple)):
            device_index = default_device[0]
        else:
            device_index = default_device

        if isinstance(device_index, int) and device_index >= 0:
            devices = sd.query_devices()
            if (
                device_index < len(devices)
                and devices[device_index]["max_input_channels"] > 0
            ):
                return device_index

        default_info = sd.query_devices(kind="input")
        default_name = str(default_info.get("name", "")).lower()
        for index, device in enumerate(sd.query_devices()):
            if (
                device["max_input_channels"] > 0
                and str(device["name"]).lower() == default_name
            ):
                return index
        return None

    def _verify_audio_device(self) -> None:
        """Check that at least one input device is available. Fail fast if not."""
        try:
            devices = sd.query_devices()
            input_devices = [d for d in devices if d["max_input_channels"] > 0]
            if not input_devices:
                raise RuntimeError(
                    "❌ No audio input devices found. "
                    "Please connect a microphone and restart."
                )
            selected = (
                sd.query_devices(self.input_device)
                if self.input_device is not None
                else sd.query_devices(kind="input")
            )
            print(
                f"🎙️ Audio device: {selected['name']} ({selected['max_input_channels']}ch)"
            )
        except RuntimeError:
            raise
        except Exception as e:
            print(f"⚠️ Could not verify audio device: {e}")

    def _maybe_switch_auto_input_device(self) -> None:
        """Follow Windows default input changes while Buddy is running."""
        if not self.auto_input_device or self._stream is None:
            return

        now = time.monotonic()
        if now - self._last_device_check < self._device_check_interval:
            return
        self._last_device_check = now

        try:
            current_default = self._current_default_input_device()
        except Exception as e:
            print(f"⚠️ Could not check default input device: {e}")
            return

        if current_default == self._active_input_device:
            return

        old_recording_state = self.is_recording
        print(
            f"🎙️ Default input changed: {self._active_input_device} → {current_default}"
        )
        self.stop_stream()
        self.input_device = current_default
        self._active_input_device = current_default
        self.is_recording = old_recording_state
        self.start_stream()

    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio stream"""
        if status:
            print(f"Audio status: {status}")
        if self.is_recording:
            # Buffer overflow protection: drop oldest if queue too large (limit to ~2s)
            if self.audio_queue.qsize() > 60:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass
            # Convert to int16 for compatibility
            audio_data = (indata[:, 0] * 32767).astype(np.int16)
            try:
                self.audio_queue.put_nowait(audio_data.tobytes())
            except queue.Full:
                pass

    def start_stream(self):
        """Start the audio input stream"""
        if self._stream is not None:
            return

        if self.auto_input_device:
            self.input_device = self._current_default_input_device()
        self._active_input_device = self.input_device

        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.float32,
            blocksize=self.chunk_size,
            device=self.input_device,
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.info("🎤 Audio stream started")

    def stop_stream(self):
        """Stop the audio input stream"""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            logger.info("🎤 Audio stream stopped")

    def start_recording(self):
        """Start recording audio to queue"""
        self.is_recording = True
        # Clear any old audio
        while not self.audio_queue.empty():
            try:
                self.audio_queue.get_nowait()
            except queue.Empty:
                break

    def stop_recording(self):
        """Stop recording audio"""
        self.is_recording = False

    @property
    def is_stream_active(self) -> bool:
        """Check if the audio input stream is currently active."""
        return self._stream is not None and self._stream.active

    def get_audio_chunk(self, timeout: float = 0.02) -> bytes | None:
        """Get an audio chunk from the queue (20ms timeout for low wake-word latency)"""
        self._maybe_switch_auto_input_device()
        try:
            return self.audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_audio_stream(self) -> Generator[bytes, None, None]:
        """Generator that yields audio chunks"""
        while self.is_recording:
            chunk = self.get_audio_chunk()
            if chunk:
                yield chunk

    @staticmethod
    def play_audio(audio_data: np.ndarray, sample_rate: int = 24000):
        """Play audio through speakers"""
        sd.play(audio_data, sample_rate)
        sd.wait()

    @staticmethod
    def play_file(filepath: str):
        """Play an audio file"""
        import wave

        with wave.open(filepath, "rb") as wf:
            data = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
            sd.play(data, wf.getframerate())
            sd.wait()


# Test function
def test_audio():
    """Test audio recording"""
    print("Testing audio for 3 seconds...")
    manager = AudioManager()
    manager.start_stream()
    manager.start_recording()

    import time

    chunks = []
    start = time.time()
    while time.time() - start < 3:
        chunk = manager.get_audio_chunk()
        if chunk:
            chunks.append(chunk)

    manager.stop_recording()
    manager.stop_stream()

    total_bytes = sum(len(c) for c in chunks)
    print(f"✅ Recorded {len(chunks)} chunks, {total_bytes} bytes")


if __name__ == "__main__":
    test_audio()
