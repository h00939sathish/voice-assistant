import onnxruntime as ort
import traceback
import sys

def test_onnx():
    print("--- Buddy ONNX Diagnostic ---")
    try:
        version = ort.get_version_string()
        print(f"✅ ONNX Runtime Version: {version}")
        
        providers = ort.get_available_providers()
        print(f"✅ Available Providers: {providers}")
        
        print("\nAttempting to access core DLL functions...")
        # This triggers the actual DLL load
        device = ort.get_device()
        print(f"✅ Device detected: {device}")
        
        print("\n[RESULT] Your ONNX DLLs appear to be working correctly.")
        
    except Exception as e:
        print("\n❌ ONNX ERROR DETECTED")
        print(f"Error Type: {type(e).__name__}")
        print(f"Error Message: {str(e)}")
        
        if "[WinError 127]" in str(e) or "procedure could not be found" in str(e).lower():
            print("\n💡 DIAGNOSIS: Found WinError 127.")
            print("This usually means 'onnxruntime' and 'onnxruntime-gpu' are conflicting.")
            print("Action: Run the cleanup commands I provided.")
        
        traceback.print_exc()

if __name__ == "__main__":
    test_onnx()
