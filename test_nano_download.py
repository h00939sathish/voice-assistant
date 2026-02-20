
try:
    from nanowakeword.utils import download_files
    print("⬇️ Calling download_lib_files()...")
    # Where does it download to? Default probably good.
    download_files.download_lib_files() 
    print("✅ Download executed")
    
    from nanowakeword import NanoInterpreter
    interpreter = NanoInterpreter(wakeword_models=['alexa']) # Try 'alexa' first as default
    print("✅ Instantiated with 'alexa'")
    
    # Try 'hey_jarvis' if available
    # Assuming it's not default based on GitHub
    # But let's check
    interpreter2 = NanoInterpreter(wakeword_models=['hey_jarvis'])
    print("✅ Instantiated with 'hey_jarvis'")

except Exception as e:
    print(f"❌ Error: {e}")
