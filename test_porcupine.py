import os
import sys
import numpy as np
import sounddevice as sd
from dotenv import load_dotenv
import pvporcupine

# Load Env
load_dotenv()

ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY")
# Using forward slashes or escaped backslashes for safety
KEYWORD_PATH = "C:/Users/h0093/Documents/new/HEY-JARVIS_en_windows_v4_0_0/HEY-JARVIS_en_windows_v4_0_0.ppn"

def test_porcupine():
    if not ACCESS_KEY:
        print("❌ Error: PICOVOICE_ACCESS_KEY not found in .env")
        return

    if not os.path.exists(KEYWORD_PATH):
        print(f"❌ Error: .ppn file not found at: {KEYWORD_PATH}")
        return

    print(f"🔄 Initializing Porcupine...")
    print(f"   Model: {KEYWORD_PATH}")

    try:
        # Initialize Porcupine
        handle = pvporcupine.create(
            access_key=ACCESS_KEY,
            keyword_paths=[KEYWORD_PATH]
        )
        
        print(f"✅ Porcupine initialized successfully!")
        print(f"   Sample Rate: {handle.sample_rate}")
        print(f"   Frame Length: {handle.frame_length}")
        print(f"\n👂 Listening for 'Hey Jarvis'... (Press Ctrl+C to stop)")

        # Create input stream
        def audio_callback(indata, frames, time, status):
            if status:
                print(f"Audio Status: {status}")
            
            # Convert to int16
            pcm = (indata * 32767).astype(np.int16).flatten()
            
            # Porcupine process
            result = handle.process(pcm)
            if result >= 0:
                print("🔥 WAKE WORD DETECTED!")

        with sd.InputStream(
            samplerate=handle.sample_rate,
            channels=1,
            dtype='float32',
            blocksize=handle.frame_length,
            callback=audio_callback
        ):
            while True:
                sd.sleep(1000)

    except Exception as e:
        print(f"❌ Failed to start Porcupine: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_porcupine()
