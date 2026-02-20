
import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from assistant.llm_router import LLMRouter
from assistant.skill_router import SkillRouter

async def test_mcp_skill():
    print("🚀 Testing MCP Skill (Desktop Commander)...")
    
    # Initialize components
    llm = LLMRouter(prefer_local=True)
    router = SkillRouter(llm_router=llm)
    router.load_skills()
    
    # Test command for Desktop Commander
    test_text = "tell desktop commander to show usage stats"
    print(f"👤 User: {test_text}")
    
    response = await router.route(test_text, {"confidence": 1.0})
    
    if response:
        print(f"🤖 Buddy (Skill): {response}")
        print("✅ SUCCESS: MCP tool executed!")
    else:
        print("❌ FAILURE: MCP skill didn't handle the request.")

if __name__ == "__main__":
    # Ensure Ollama is running or it will fail
    asyncio.run(test_mcp_skill())
