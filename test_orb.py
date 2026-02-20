
import time
from assistant.orb_overlay import OrbOverlay

def test_orb():
    print("🔮 Starting Orb Overlay Test...")
    orb = OrbOverlay()
    orb.start()
    
    states = ["idle", "listening", "processing", "speaking", "idle", "hidden"]
    
    try:
        for state in states:
            print(f"   -> State: {state.upper()}")
            orb.set_state(state)
            time.sleep(2)
            
    except KeyboardInterrupt:
        pass
    finally:
        print("🛑 Stopping Orb...")
        orb.stop()
        print("✅ Test Complete")

if __name__ == "__main__":
    test_orb()
