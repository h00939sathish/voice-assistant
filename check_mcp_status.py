import asyncio
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from config import MCP_SERVERS
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

async def check_mcp_status():
    print("🔌 Checking MCP Server Connection Status...")
    
    if not HAS_MCP:
        print("❌ ERROR: 'mcp' Python package is not installed.")
        return

    if not MCP_SERVERS:
        print("⚠️ WARNING: No MCP servers configured in config.py")
        return

    for name, config in MCP_SERVERS.items():
        print(f"\n--- Server: {name} ---")
        command = config.get("command")
        args = config.get("args", [])
        env = config.get("env")
        
        print(f"👉 Command: {command} {' '.join(args)}")
        
        try:
            # Attempt a 10-second timeout for connection
            async with asyncio.timeout(10):
                async with stdio_client(StdioServerParameters(command=command, args=args, env=env)) as (read, write):
                    async with ClientSession(read, write) as session:
                        print("📡 Attempting initialization...")
                        await session.initialize()
                        
                        print("🔍 Listing tools...")
                        tools_result = await session.list_tools()
                        tool_count = len(tools_result.tools)
                        
                        print(f"✅ SUCCESS: Connected to {name}")
                        print(f"🛠️  Available Tools: {tool_count}")
                        if tool_count > 0:
                            top_tools = [t.name for t in tools_result.tools[:5]]
                            print(f"📦 Sample Tools: {', '.join(top_tools)}...")
                            
        except asyncio.TimeoutError:
            print(f"❌ FAILED: Connection to {name} timed out.")
        except Exception as e:
            print(f"❌ FAILED: Could not connect to {name}.")
            print(f"   Error details: {e}")

if __name__ == "__main__":
    asyncio.run(check_mcp_status())