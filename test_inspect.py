
import nanowakeword
print(f"Module: {nanowakeword}")
print(f"Dir: {dir(nanowakeword)}")
try:
    from nanowakeword import NanoWakeWord
    print("Found NanoWakeWord")
except ImportError:
    pass
