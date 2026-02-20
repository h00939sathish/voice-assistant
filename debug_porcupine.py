
import os
import sys
import struct
import time
from dotenv import load_dotenv

# Load env vars
load_dotenv(override=True)

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import PICOVOICE_ACCESS_KEY, PORCUPINE_KEYWORD_PATH
from assistant.audio_manager import AudioManager

def debug_porcupine():
    print("------------------------------------------------")
    print("       🦔 PORCUPINE DEBUGGER 🦔")
    print("------------------------------------------------")
    
    # 1. Check Key
    if not PICOVOICE_ACCESS_KEY:
        print("❌ Error: PICOVOICE_ACCESS_KEY not found in environment variables.")
        return
    print(f"✅ Access Key found: {PICOVOICE_ACCESS_KEY[:10]}...")

    # 2. Check File
    if not os.path.exists(PORCUPINE_KEYWORD_PATH):
        print(f"❌ Error: Keyword file not found at: {PORCUPINE_KEYWORD_PATH}")
        return
    print(f"✅ Keyword file found: {PORCUPINE_KEYWORD_PATH}")

    # 3. Import and Load
    try:
        import pvporcupine
        print(f"✅ pvporcupine imported")
    except ImportError:
        print("❌ Error: pvporcupine package not installed. Run 'pip install pvporcupine'")
        return

    try:
        porcupine = pvporcupine.create(
            access_key=PICOVOICE_ACCESS_KEY,
            keyword_paths=[str(PORCUPINE_KEYWORD_PATH)]
        )
        print("✅ Porcupine engine initialized successfully with CUSTOM model!")
    except Exception as e:
        print(f"❌ Error initializing Custom Model: {e}")
        print("🔄 Attempting fallback to default 'jarvis' keyword...")
        try:
            porcupine = pvporcupine.create(
                access_key=PICOVOICE_ACCESS_KEY,
                keywords=["jarvis"]
            )
            print("✅ Porcupine engine initialized successfully with DEFAULT model!")
        except Exception as e2:
            print(f"❌ Error initializing Default Model: {e2}")
            print("⚠️ Check your Access Key and Internet Connection.")
            return

    # 4. Audio Loop
    audio = AudioManager()
    print("\n🎤 Opening audio stream...")
    audio.start_stream()
    audio.start_recording()

    print(f"\n👂 Listening for 'Hey Jarvis'...")
    print("   Press Ctrl+C to stop.")

    try:
        while True:
            chunk = audio.get_audio_chunk()
            if chunk:
                # Process
                pcm = struct.unpack_from("h" * porcupine.frame_length, chunk)
                result = porcupine.process(pcm)
                
                if result >= 0:
                    print(f"   🎉 WAKE WORD DETECTED! (Index: {result})")
            else:
                time.sleep(0.01)

    except KeyboardInterrupt:
        print("\n🛑 Stopping...")
    except Exception as e:
        print(f"\n❌ Error in loop: {e}")
    finally:
        if porcupine:
            porcupine.delete()
        if audio:
            audio.stop_recording()
            audio.stop_stream()
        print("Done.")

if __name__ == "__main__":
    debug_porcupine()
