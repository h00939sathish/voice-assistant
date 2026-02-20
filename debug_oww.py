
import os
import sys
import numpy as np
import openwakeword
from openwakeword.model import Model
from assistant.audio_manager import AudioManager
import time

def debug_oww():
    print("------------------------------------------------")
    print("       🌊 OPENWAKEWORD DEBUGGER 🌊")
    print("------------------------------------------------")
    
    # 1. Download/Load
    print("⬇️  Checking models...")
    try:
        openwakeword.utils.download_models()
        print("✅ Models downloaded/verified.")
    except Exception as e:
        print(f"⚠️ Warning downloading models: {e}")

    # 2. Initialize
    print("🔄 Loading 'hey_jarvis' model...")
    try:
        # Load specific model
        oww_model = Model(
            wakeword_models=["hey_jarvis"],
            inference_framework="onnx"
        )
        print("✅ openWakeWord engine initialized!")
        print(f"   - Models: {oww_model.models.keys()}")
    except Exception as e:
        print(f"❌ Error initializing openWakeWord: {e}")
        return

    # 3. Audio Loop
    audio = AudioManager()
    print("\n🎤 Opening audio stream...")
    audio.start_stream()
    audio.start_recording()

    print(f"\n👂 Listening for 'HEY JARVIS'...")
    print("   (Confidence Threshold: 0.5)")
    print("   Press Ctrl+C to stop.")

    try:
        while True:
            chunk = audio.get_audio_chunk()
            if chunk:
                # Convert to int16 then float32
                audio_data = np.frombuffer(chunk, dtype=np.int16)
                
                # Feed to model
                prediction = oww_model.predict(audio_data)
                
                for mdl, score in oww_model.prediction_buffer.items():
                    if score[-1] > 0.5:
                        print(f"   🎉 WAKE WORD DETECTED! ({mdl}: {score[-1]:.3f})")
                        oww_model.reset()
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    except Exception as e:
        print(f"\n❌ Error in loop: {e}")
    finally:
        audio.stop_recording()
        audio.stop_stream()
        print("Done.")

if __name__ == "__main__":
    debug_oww()
