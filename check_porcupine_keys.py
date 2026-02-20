import os
from dotenv import load_dotenv
import pvporcupine

load_dotenv()
ACCESS_KEY = os.getenv("PICOVOICE_ACCESS_KEY")

def check_keys():
    if not ACCESS_KEY:
        print("❌ Error: PICOVOICE_ACCESS_KEY not found in .env")
        return

    print(f"Testing AccessKey: {ACCESS_KEY[:10]}...")
    try:
        # Try to load a built-in keyword
        handle = pvporcupine.create(
            access_key=ACCESS_KEY,
            keywords=['jarvis']
        )
        print("✅ Success! Your AccessKey is valid and active for standard models.")
        handle.delete()
    except Exception as e:
        print(f"❌ Failed: {e}")
        print("\nDiagnostic Info:")
        print("- Please log in to https://console.picovoice.ai/ to verify your key.")
        print("- Ensure your internet connection is active for the first activation.")

if __name__ == "__main__":
    check_keys()
