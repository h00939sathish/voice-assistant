
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from assistant.proactive_engine import ProactiveEngine
    engine = ProactiveEngine()
    print("✅ ProactiveEngine initialized successfully")
    print(f"   Check Interval: {engine.settings['CHECK_INTERVAL']}")
    
    # Mock check
    import time
    engine.last_check = time.time() - 3600 # Force check
    
    # Mock battery if possible, or just run check (should return None or trigger)
    trigger = engine.check_triggers(time.time())
    print(f"   Trigger check result: {trigger}")
    
except Exception as e:
    print(f"❌ Failed: {e}")
    import traceback
    traceback.print_exc()
