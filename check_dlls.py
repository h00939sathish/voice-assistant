
import sys
import traceback

def check_import(name):
    print(f"Checking {name}...")
    try:
        __import__(name)
        print(f"✅ {name} imported successfully.")
        return True
    except Exception as e:
        print(f"❌ {name} failed: {e}")
        traceback.print_exc()
        return False

def check_onnx():
    print("Checking ONNX Runtime...")
    try:
        import onnxruntime as ort
        print(f"✅ onnxruntime version: {ort.__get_version__()}")
        print(f"   Available providers: {ort.get_available_providers()}")
    except Exception as e:
        print(f"❌ onnxruntime failed: {e}")
        traceback.print_exc()

if __name__ == "__main__":
    print("--- Buddy DLL Diagnostic ---")
    check_import("torch")
    check_import("faster_whisper")
    check_onnx()
    check_import("openwakeword")
    check_import("vosk")
