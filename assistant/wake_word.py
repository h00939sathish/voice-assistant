"""
Wake Word Detection using openWakeWord or Porcupine
"""
import numpy as np
from typing import Callable, Optional
import sys
import os
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    WAKE_WORD_MODEL, WAKE_WORD_THRESHOLD, 
    PICOVOICE_ACCESS_KEY, PORCUPINE_KEYWORD_PATH
)

class WakeWordDetector:
    """Detects wake word using openWakeWord (Primary) or Vosk (Fallback)"""
    
    def __init__(self, on_wake: Optional[Callable] = None):
        self.threshold = WAKE_WORD_THRESHOLD
        self.on_wake = on_wake
        self.oww_model = None
        self.vosk_rec = None
        self.use_vosk = False
        self._chunk_counter = 0  # For rate limiting
        self._loading_lock = threading.Lock()
        self._is_loaded = False
        
    def load_model(self):
        """Load the wake word models (thread-safe)"""
        with self._loading_lock:
            if self._is_loaded:
                return
            
            # 1. openWakeWord (Modern Neural - Primary)
            print("🔄 Loading openWakeWord engine (Primary)...")
            try:
                import openwakeword
                try:
                    openwakeword.utils.download_models()
                except Exception as e:
                    print(f"⚠️ Model download skipped/failed: {e}")

                from openwakeword.model import Model
                try:
                    self.oww_model = Model(
                        wakeword_models=[WAKE_WORD_MODEL],
                        inference_framework="onnx"
                    )
                    self._is_loaded = True
                    print(f"✅ openWakeWord loaded: '{WAKE_WORD_MODEL}'")
                    return # Successfully loaded primary
                except Exception as e:
                    print(f"⚠️ openWakeWord error: {e}")
                    print("   Trying fallback neural model...")
                    try:
                        self.oww_model = Model(
                            wakeword_models=["alexa_v0.1"],
                            inference_framework="onnx"
                        )
                        self._is_loaded = True
                        print("✅ openWakeWord loaded: 'alexa_v0.1' (Fallback)")
                        return
                    except Exception as e2:
                        print(f"⚠️ Neural fallback failed: {e2}")
                    
            except Exception as e:
                print(f"❌ openWakeWord critical failure: {e}")

            # 2. Vosk (Reliable Speech-to-Text Fallback)
            print("🔄 Loading Vosk engine (Fallback)...")
            try:
                from vosk import Model, KaldiRecognizer, SetLogLevel
                SetLogLevel(-1) # Silence logs
                
                try:
                    self.vosk_model = Model(model_name="vosk-model-small-en-us-0.15")
                except Exception:
                     print("   Downloading Vosk model...")
                     self.vosk_model = Model(lang="en-us") 
                
                self.vosk_rec = KaldiRecognizer(self.vosk_model, 16000, '["hey jarvis", "[unk]"]')
                self.use_vosk = True
                self._is_loaded = True
                print("✅ Vosk loaded! (Keyword: 'hey jarvis')")
                return
            except Exception as e:
                print(f"⚠️ Vosk failed: {e}")
            
            print("❌ All wake word engines failed to load.")

    def process_audio(self, audio_chunk: bytes) -> bool:
        """Process audio chunk (will auto-load if not ready)"""
        if not self._is_loaded:
            if not self._loading_lock.locked():
                threading.Thread(target=self.load_model, daemon=True).start()
            return False

        self._chunk_counter += 1
        if self._chunk_counter % 2 != 0:
            return False

        # Try Primary (openWakeWord)
        if self.oww_model:
            if self._process_oww(audio_chunk):
                return True
        
        # Try Fallback (Vosk)
        if self.use_vosk and self.vosk_rec:
            if self._process_vosk(audio_chunk):
                return True
                
        return False

    def _process_vosk(self, audio_chunk: bytes) -> bool:
        """Process using Vosk (Grammar Mode)"""
        if self.vosk_rec.AcceptWaveform(audio_chunk):
            res = self.vosk_rec.Result()
            if "hey jarvis" in res:
                print("🎯 Wake word detected (Vosk)!")
                if self.on_wake:
                    self.on_wake()
                return True
        return False

    def _process_oww(self, audio_chunk: bytes) -> bool:
        """Process using openWakeWord"""
        if self.oww_model is None:
            self.load_model()
        
        audio_data = np.frombuffer(audio_chunk, dtype=np.int16)
        audio_float = audio_data.astype(np.float32) / 32768.0
        
        prediction = self.oww_model.predict(audio_float)
        
        for model_name, score in self.oww_model.prediction_buffer.items():
            if len(score) > 0 and score[-1] > self.threshold:
                print(f"🎯 Wake word detected! Score: {score[-1]:.3f}")
                self.oww_model.reset()
                if self.on_wake:
                    self.on_wake()
                return True
        return False
    
    def reset(self):
        """Reset the wake word buffer"""
        if self.oww_model:
            self.oww_model.reset()


def test_wake_word():
    """Test wake word detection"""
    from .audio_manager import AudioManager
    import time
    
    detected = False
    
    def on_wake():
        nonlocal detected
        detected = True
        print("🎉 WAKE WORD DETECTED!")
    
    detector = WakeWordDetector(on_wake=on_wake)
    detector.load_model()
    
    audio = AudioManager()
    audio.start_stream()
    audio.start_recording()
    
    print("\n👂 Listening for 'Hey Jarvis'... (10 seconds)")
    print("   Say the wake word to test detection.\n")
    
    start = time.time()
    while time.time() - start < 10 and not detected:
        chunk = audio.get_audio_chunk()
        if chunk:
            detector.process_audio(chunk)
    
    audio.stop_recording()
    audio.stop_stream()
    
    if detected:
        print("✅ Test passed!")
    else:
        print("❌ No wake word detected in 10 seconds")


if __name__ == "__main__":
    test_wake_word()
