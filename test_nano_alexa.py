
try:
    from nanowakeword import NanoInterpreter
    
    print("Trying 'alexa'...")
    try:
        ni = NanoInterpreter(wakeword_models=["alexa"])
        print("✅ Success with 'alexa'")
    except Exception as e:
        print(f"❌ Failed 'alexa': {e}")
        
    print("Trying 'hey_jarvis'...")
    try:
        ni = NanoInterpreter(wakeword_models=["hey_jarvis"])
        print("✅ Success with 'hey_jarvis'")
    except Exception as e:
        print(f"❌ Failed 'hey_jarvis': {e}")

except Exception as e:
    print(f"❌ Error: {e}")
