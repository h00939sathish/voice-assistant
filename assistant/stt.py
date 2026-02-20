"""
Speech-to-Text using faster-whisper with Silero VAD
"""
import numpy as np
from faster_whisper import WhisperModel
import torch
from typing import Optional, Tuple, List
import sys
import os
import time
import threading

from assistant.interfaces import ISTTProvider, IAudioManager

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import (
    WHISPER_MODEL, WHISPER_DEVICE, WHISPER_COMPUTE_TYPE,
    SAMPLE_RATE, VAD_THRESHOLD, SILENCE_DURATION_MS, MIN_SPEECH_DURATION_MS
)


class SpeechToText(ISTTProvider):
    """Speech-to-Text with VAD-based endpoint detection"""
    
    def __init__(self):
        self.whisper_model: Optional[WhisperModel] = None
        self.vad_model = None
        self.vad_utils = None
        self._audio_buffer: List[bytes] = []
        self._loading_lock = threading.Lock()
        self._is_loaded = False
        
    def load_models(self):
        """Load Whisper and VAD models (thread-safe)"""
        with self._loading_lock:
            if self._is_loaded:
                return
                
            print("🔄 Loading STT models...")
            
            # 1. Load faster-whisper
            try:
                self.whisper_model = WhisperModel(
                    WHISPER_MODEL,
                    device=WHISPER_DEVICE,
                    compute_type=WHISPER_COMPUTE_TYPE
                )
                print(f"   ✅ Whisper model: {WHISPER_MODEL} ({WHISPER_DEVICE.upper()})")
            except Exception as e:
                print(f"   ❌ Whisper load failed: {e}")

            # 2. Load Silero VAD (Safe Mode: pure torch)
            try:
                self.vad_model, self.vad_utils = torch.hub.load(
                    repo_or_dir='snakers4/silero-vad',
                    model='silero_vad',
                    force_reload=False,
                    onnx=False
                )
                self.vad_model.to('cpu')
                print("   ✅ Silero VAD loaded (Safe Mode)")
            except Exception as e:
                print(f"   ⚠️ Silero VAD failed ({e}). Switching to Energy Fallback.")
                self.vad_model = None # Trigger Energy Fallback in listen logic
            
            self._is_loaded = True

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
                pass # Fall through to energy check
        
        # 2. Fallback: Simple RMS Energy Detection
        # Calculate Root Mean Square energy
        rms = np.sqrt(np.mean(audio_int16.astype(np.float64)**2))
        # Map RMS ~100-1000 to 0.0-1.0 probability
        # (Typical silence is < 50, speech is > 300)
        prob = min(1.0, max(0.0, (rms - 100) / 500))
        return prob
    
    def listen_with_vad(self, audio_manager: IAudioManager, max_duration: float = 15.0) -> Optional[bytes]:
        """
        Listen for speech using VAD to detect when user stops speaking
        """
        if not self._is_loaded:
            self.load_models()
        
        self._audio_buffer = []
        silence_samples = 0
        speech_samples = 0
        samples_per_chunk = 512  # ~32ms at 16kHz
        silence_threshold = int(SILENCE_DURATION_MS * SAMPLE_RATE / 1000 / samples_per_chunk)
        min_speech_threshold = int(MIN_SPEECH_DURATION_MS * SAMPLE_RATE / 1000 / samples_per_chunk)
        
        start_time = time.time()
        has_speech = False
        
        print("👂 Listening... (speak now)")
        
        while time.time() - start_time < max_duration:
            chunk = audio_manager.get_audio_chunk(timeout=0.1)
            if chunk is None:
                continue
            
            self._audio_buffer.append(chunk)
            speech_prob = self._check_speech(chunk)
            
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
                        print("   🔇 Silence detected, processing...")
                        break
        
        if not has_speech:
            print("   ⚠️ No speech detected")
            return None
        
        # Combine all audio chunks
        return b''.join(self._audio_buffer)
    
    def transcribe(self, audio_bytes: bytes) -> Tuple[str, float]:
        """
        Transcribe audio bytes to text
        """
        if self.whisper_model is None:
            self.load_models()
        
        if self.whisper_model is None:
            return "Error: STT model not loaded", 0.0

        # Convert to numpy float32
        audio_int16 = np.frombuffer(audio_bytes, dtype=np.int16)
        audio_float = audio_int16.astype(np.float32) / 32768.0
        
        # Transcribe
        segments, info = self.whisper_model.transcribe(
            audio_float,
            language=None, # Auto-detect language
            vad_filter=True,
            vad_parameters=dict(
                min_silence_duration_ms=500,
                speech_pad_ms=200
            ) 
        )
        
        # Log detected language
        if info.language != "en":
              print(f"   🌍 Detected language: {info.language} ({info.language_probability:.0%})")
        
        # Collect transcription
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
