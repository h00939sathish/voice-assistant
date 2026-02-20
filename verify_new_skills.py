
import sys
import asyncio
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from assistant.skills_registry import registry
from assistant.skill_router import SkillRouter

async def test_skills():
    print("🧪 Verifying New Personal Assistant Skills...")
    
    # Initialize router (this loads skills)
    router = SkillRouter()
    router.load_skills()
    
    # 1. Test FileManager
    print("\n[Test 1] FileManagerSkill")
    file_skill = registry.create_instance("file_manager")
    if file_skill:
        response = await file_skill.handle("list files here", {})
        print(f"✅ 'list files here':\n{response[:100]}...")
        
        response = await file_skill.handle("find file requirements.txt", {})
        print(f"✅ 'find file requirements.txt':\n{response[:100]}...")
    else:
        print("❌ FileManagerSkill not loaded!")

    # 2. Test SystemMonitor
    print("\n[Test 2] SystemMonitorSkill")
    sys_skill = registry.create_instance("system_monitor")
    if sys_skill:
        response = await sys_skill.handle("cpu usage", {})
        print(f"✅ 'cpu usage': {response}")
        
        response = await sys_skill.handle("battery status", {})
        print(f"✅ 'battery status': {response}")
    else:
        print("❌ SystemMonitorSkill not loaded!")

if __name__ == "__main__":
    asyncio.run(test_skills())
