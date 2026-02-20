"""
MCP Skill - Bridge to Model Context Protocol Servers
"""
import logging
import os
import sys
import json
from typing import Dict, Any, List, Optional

# Add project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import MCP_SERVERS
from assistant.skills_registry import skill

# Import MCP SDK
try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
    HAS_MCP = True
except ImportError:
    HAS_MCP = False

logger = logging.getLogger(__name__)

@skill(
    name="mcp",
    keywords=["use", "ask", "tell", "run", "search", "check"],
    description="Executes tools from Model Context Protocol (MCP) servers like Desktop Commander or GitHub",
    priority=10 # Much higher priority to catch specific tool requests
)
class MCPSkill:
    """
    Connects to local MCP servers and exposes their tools to the assistant.
    """
    
    def __init__(self):
        self.available_tools = {}
        self._llm_router = None # Will be set by router if needed, or we use internal logic

    async def handle(self, text: str, context: Dict[str, Any]) -> str:
        """
        Handle user requests by routing to MCP tools.
        """
        if not HAS_MCP:
            return "MCP SDK is missing. Please run 'pip install mcp'."

        # 1. Determine which server to use
        # For now, we'll check each configured server to see if it can help
                # In a more advanced version, we'd cache tool definitions and use LLM to pick.
        
                for server_name, config in MCP_SERVERS.items():            # If the user explicitly mentioned the server name, prioritize it
            # Otherwise, we might check all servers if the request is generic
            if server_name.lower().replace("_", " ") in text.lower() or len(MCP_SERVERS) == 1:
                res = await self._try_execute_on_server(server_name, config, text)
                if res:
                    return res # Return the first successful tool execution
        
        # If no explicit match, try the first server (likely Desktop Commander)
        if MCP_SERVERS:
            server_name = list(MCP_SERVERS.keys())[0]
            res = await self._try_execute_on_server(server_name, MCP_SERVERS[server_name], text)
            if res:
                return res

        return "I have MCP tools configured, but I couldn't find a specific tool for that request. Try saying 'tell desktop commander to check disk'."

    async def _try_execute_on_server(self, name: str, config: Dict[str, Any], text: str) -> Optional[str]:
        """Connect to a server and try to find/execute a matching tool"""
        command = config.get("command")
        args = config.get("args", [])
        env = config.get("env", None)
        
        try:
            async with stdio_client(StdioServerParameters(command=command, args=args, env=env)) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    
                    # 1. List tools
                    tools_result = await session.list_tools()
                    tools = tools_result.tools
                    
                    if not tools:
                        return None

                    # 2. Use LLM to pick a tool and arguments
                    # We need access to an LLM here. We'll use Ollama or Gemini if available.
                    # Since we don't have easy access to the main LLMRouter here without passing it in,
                    # we will try to use a fast local model via Ollama.
                    
                    tool_call = await self._decide_tool_call(text, tools, name)
                    
                    if not tool_call or tool_call.get("tool") == "none":
                        return None
                    
                    tool_name = tool_call["tool"]
                    tool_args = tool_call.get("arguments", {})
                    
                    print(f"   🔧 MCP [{name}] executing: {tool_name}({tool_args})")
                    
                    # 3. Call the tool
                    result = await session.call_tool(tool_name, tool_args)
                    
                    # 4. Format the result (it's usually a list of content blocks)
                    response_text = ""
                    for content in result.content:
                        if hasattr(content, "text"):
                            response_text += content.text
                        elif isinstance(content, dict) and "text" in content:
                            response_text += content["text"]
                            
                    return response_text

        except Exception as e:
            logger.error(f"MCP Error [{name}]: {e}")
            return f"Error communicating with {name}: {e}"

    async def _decide_tool_call(self, text: str, tools: List[Any], server_name: str) -> Optional[Dict[str, Any]]:
        """Ask LLM to pick a tool and arguments from the list"""
        # Format tools for prompt
        tool_defs = []
        for t in tools:
            tool_defs.append({
                "name": t.name,
                "description": t.description,
                "inputSchema": t.inputSchema
            })
            
        prompt = f"""SYSTEM: You are a tool-routing assistant for the '{server_name}' MCP server.
Task: Pick the BEST tool from the list to handle the user's request.
Output: You MUST respond with ONLY a raw JSON object. NO markdown, NO explanation, NO code blocks.

Available Tools:
{json.dumps(tool_defs, indent=2)}

User Request: "{text}"

Target JSON Format:
{{
  "tool": "tool_name",
  "arguments": {{ "arg1": "val1" }}
}}
(If no tool matches, return {{"tool": "none"}})"""

        try:
            # Try fast local inference for tool routing
            import ollama
            
            # Find an available model
            ollama_resp = ollama.list()
            models_list = getattr(ollama_resp, 'models', ollama_resp)
            available_models = []
            for m in models_list:
                if isinstance(m, dict):
                    available_models.append(m.get('name', m.get('model', '')))
                else:
                    available_models.append(getattr(m, 'model', getattr(m, 'name', '')))
            
            # Prioritize robust models
            best_model_base = next((m for m in ["qwen2.5", "llama3.1", "llama3.2", "mistral", "gemma", "phi3"] if any(m in am for am in available_models)), None)
            
            if best_model_base:
                # Find the actual full name (e.g. llama3.2:3b)
                best_model = next((am for am in available_models if best_model_base in am), best_model_base)
            elif available_models:
                best_model = available_models[0]
            else:
                best_model = "llama3.2"

            response = ollama.chat(
                model=best_model,
                messages=[{"role": "user", "content": prompt}],
                options={"num_predict": 256, "temperature": 0}
            )
            
            raw = response["message"]["content"].strip()
            
            # Robust JSON extraction
            json_start = raw.find('{')
            json_end = raw.rfind('}')
            if json_start != -1 and json_end != -1:
                raw = raw[json_start:json_end+1]
            
            return json.loads(raw)
        except Exception as e:
            logger.error(f"Tool decision failed: {e}")
            return None