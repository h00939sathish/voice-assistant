"""
Audio Manager - Handles microphone input and speaker output
"""
import numpy as np
import sounddevice as sd
import queue
from typing import Optional, Generator
import sys
import os

from assistant.interfaces import IAudioManager

# Add parent to path for config
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import SAMPLE_RATE, CHANNELS, CHUNK_SIZE


class AudioManager(IAudioManager):
    """Manages audio input/output streams"""
    
    def __init__(self):
        self.sample_rate = SAMPLE_RATE
        self.channels = CHANNELS
        self.chunk_size = CHUNK_SIZE
        self.audio_queue: queue.Queue = queue.Queue()
        self.is_recording = False
        self._stream: Optional[sd.InputStream] = None
        
    def _audio_callback(self, indata, frames, time, status):
        """Callback for audio stream"""
        if status:
            print(f"Audio status: {status}")
        if self.is_recording:
            # Buffer overflow protection: drop oldest if queue too large
            if self.audio_queue.qsize() > 100:
                try:
                    self.audio_queue.get_nowait()
                except queue.Empty:
                    pass
            # Convert to int16 for compatibility
            audio_data = (indata[:, 0] * 32767).astype(np.int16)
            self.audio_queue.put(audio_data.tobytes())
    
    def start_stream(self):
        """Start the audio input stream"""
        if self._stream is not None:
            return
            
        self._stream = sd.InputStream(
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype=np.float32,
            blocksize=self.chunk_size,
            callback=self._audio_callback
        )
        self._stream.start()
        print("🎤 Audio stream started")
    
    def stop_stream(self):
        """Stop the audio input stream"""
        if self._stream is not None:
            self._stream.stop()
            self._stream.close()
            self._stream = None
            print("🎤 Audio stream stopped")
    
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
    
    def get_audio_chunk(self, timeout: float = 0.1) -> Optional[bytes]:
        """Get an audio chunk from the queue"""
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
        with wave.open(filepath, 'rb') as wf:
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
