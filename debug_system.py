"""
Debug script to check system connections
"""
import os
from dotenv import load_dotenv

# Force reload of .env
load_dotenv(override=True)

def check_env():
    print("\n🔍 Checking Environment Variables...")
    keys = [
        "GEMINI_API_KEY", 
        "GOOGLE_API_KEY",
        "PICOVOICE_ACCESS_KEY", 
        "OLLAMA_MODEL",
        "GROQ_API_KEY",
        "NVIDIA_API_KEY",
        "OPENROUTER_API_KEY"
    ]
    
    for key in keys:
        val = os.getenv(key)
        status = "✅ Found" if val else "❌ Missing"
        print(f"   {key}: {status}")
        if val and "KEY" in key:
             print(f"      (Ends with: ...{val[-4:]})")
        if key == "PICOVOICE_ACCESS_KEY" and val:
            print(f"   (Key length: {len(val)})")

def check_ollama():
    print("\n🦙 Checking Ollama...")
    try:
        import ollama
        response = ollama.list()
        print("   ✅ Connection successful")
        
        available_models = []
        models_list = getattr(response, 'models', []) or response
        for m in models_list:
            if isinstance(m, dict):
                name = m.get('name') or m.get('model')
            else:
                name = getattr(m, 'model', None) or getattr(m, 'name', None)
            if name:
                available_models.append(name)
        
        target_model = os.getenv("OLLAMA_MODEL", "llama3.2")
        found = any(target_model in m for m in available_models)
        print(f"   Found models: {available_models}")
        
    except Exception as e:
        print(f"   ❌ Connection failed: {e}")

def check_groq():
    print("\n⚡ Checking Groq...")
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key: return

    try:
        from groq import Groq
        client = Groq(api_key=api_key)
        completion = client.chat.completions.create(
            model="llama-3.1-8b-instant",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10
        )
        print("   ✅ Groq Success")
    except Exception as e:
        print(f"   ❌ Groq Failed: {e}")

def check_nvidia():
    print("\n🟢 Checking Nvidia NIM...")
    api_key = os.getenv("NVIDIA_API_KEY")
    if not api_key: return

    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://integrate.api.nvidia.com/v1", api_key=api_key)
        completion = client.chat.completions.create(
            model="meta/llama-3.1-70b-instruct",
            messages=[{"role": "user", "content": "Hi"}],
            max_tokens=10
        )
        print("   ✅ Nvidia Success")
    except Exception as e:
        print(f"   ❌ Nvidia Failed: {e}")

def check_openrouter():
    print("\n🦄 Checking OpenRouter...")
    api_key = os.getenv("OPENROUTER_API_KEY")
    if not api_key: return

    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)
        completion = client.chat.completions.create(
            model="google/gemini-2.0-flash-exp:free", # Matches config.py
            messages=[{"role": "user", "content": "Hi"}],
            extra_headers={"HTTP-Referer": "https://github.com/buddy-assistant"},
        )
        print("   ✅ OpenRouter Success")
    except Exception as e:
        print(f"   ❌ OpenRouter Failed: {e}")

def check_gemini():
    print("\n✨ Checking Gemini...")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key: return
        
    try:
        from google import genai
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.0-flash", contents="Hi"
        )
        print("   ✅ Gemini Success")
    except Exception as e:
        print(f"   ❌ Gemini Failed (likely quota): {e}")

if __name__ == "__main__":
    print("=== System Diagnostic Tool ===")
    check_env()
    check_ollama()
    check_groq()
    check_nvidia()
    check_openrouter()
    check_gemini()
    print("\n==============================")
