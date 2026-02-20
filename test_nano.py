
try:
    from nanowakeword.utils import download_files
    print("⬇️ Downloading models...")
    download_files()
    print("✅ Download complete")
    
    from nanowakeword import NanoInterpreter
    print("🏗️ Instantiating NanoInterpreter with 'hey_jarvis'...")
    try:
        # Try different potential model names if "hey_jarvis" fails
        # Assuming typical model name format for this lib
        # Usually built-in models are "alexa", "hey_google", "hey_jarvis" etc
        n = NanoInterpreter(wakeword_models=["hey_jarvis"])
        print("✅ Instantiated successfully!")
        
        # Test processing
        import numpy as np
        chunk = np.zeros(1280, dtype=np.int16) # 80ms chunk (typical for nw)
        # NanoInterpreter process expects input? Or __call__?
        # Based on args, let's guess predict or __call__
        # Or look at dir(n)
        print(f"Methods: {[m for m in dir(n) if not m.startswith('_')]}")
        
    except Exception as e:
        print(f"❌ Instantiation failed: {e}")
        # Try checking for model files in local dir?
        import os
        print(f"Current dir files: {os.listdir('.')}")

except Exception as e:
    print(f"❌ Error: {e}")
