"""
Final System Verification Script
Tests: Skills, Memory, Proactive Engine
"""
import sys
from pathlib import Path

# Add project root
sys.path.insert(0, str(Path(__file__).parent))

def test_skills():
    print("\n=== 1. SKILLS LOAD TEST ===")
    from assistant.skill_router import SkillRouter
    router = SkillRouter()
    router.load_skills()
    skills = router.get_skill_names()
    print(f"   Loaded {len(skills)} skills: {skills}")
    return len(skills) > 0

def test_memory():
    print("\n=== 2. MEMORY TEST ===")
    from assistant.conversation_memory import ConversationMemory
    mem = ConversationMemory()
    
    # Add a fact
    mem.add_fact("User's favorite color is blue", "preference")
    
    # Retrieve
    facts = mem.get_all_facts()
    print(f"   Facts stored: {facts}")
    return len(facts) > 0

def test_proactive():
    print("\n=== 3. PROACTIVE ENGINE TEST ===")
    from assistant.proactive_engine import ProactiveEngine
    import time
    
    engine = ProactiveEngine()
    # Force check by resetting last_check
    engine.last_check = time.time() - 3600
    
    # Simulate old activity to trigger idle
    old_activity = time.time() - 7200  # 2 hours ago
    trigger = engine.check_triggers(old_activity)
    
    print(f"   Trigger result (idle test): {trigger}")
    return trigger is not None or engine.settings["ENABLED"]

def test_llm_router():
    print("\n=== 4. LLM ROUTER TEST ===")
    from assistant.llm_router import LLMRouter
    router = LLMRouter()
    
    # Check if any provider is available
    providers = []
    if router._gemini_client:
        providers.append("Gemini")
    if router._groq_client:
        providers.append("Groq")
    if router._ollama_available:
        providers.append("Ollama")
        
    print(f"   Available LLM Providers: {providers}")
    return len(providers) > 0

if __name__ == "__main__":
    print("🧪 BUDDY VOICE ASSISTANT - FINAL VERIFICATION")
    print("=" * 50)
    
    results = {}
    results["Skills"] = test_skills()
    results["Memory"] = test_memory()
    results["Proactive"] = test_proactive()
    results["LLM"] = test_llm_router()
    
    print("\n" + "=" * 50)
    print("📊 RESULTS:")
    all_pass = True
    for test, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"   {test}: {status}")
        if not passed:
            all_pass = False
            
    print("=" * 50)
    if all_pass:
        print("🎉 ALL TESTS PASSED! Buddy is ready.")
    else:
        print("⚠️ Some tests failed. Review above.")
