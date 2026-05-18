"""
Core Buddy Agent System
Unified interface for agents, tools, and task execution.
"""

import logging

from .agents.general_agents import CodeCompanionAgent, FileOpsAgent, GeneralAgent
from .agents.registry import AgentRegistry
from .agents.task_router import TaskRouter
from .tools import ALL_TOOLS
from .tools.base import ToolResult
from .tools.registry import ToolRegistry

logger = logging.getLogger(__name__)


class BuddyCore:
    """
    Central system that ties together all agents and tools.
    This is the main entry point for Buddy's task execution.
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if hasattr(self, "_initialized"):
            return

        self._initialized = True
        self.tool_registry = ToolRegistry()
        self.agent_registry = AgentRegistry()
        self.task_router: TaskRouter | None = None
        self._llm = None

        self._register_default_tools()
        self._register_default_agents()

    def _register_default_tools(self):
        for tool in ALL_TOOLS:
            self.tool_registry.register(tool)
        logger.info(f"Registered {len(ALL_TOOLS)} default tools")

    def _register_default_agents(self):
        self.agent_registry.register("general", GeneralAgent)
        self.agent_registry.register("code_companion", CodeCompanionAgent)
        self.agent_registry.register("file_ops", FileOpsAgent)
        logger.info("Registered default agents")

    def set_llm(self, llm_provider):
        self._llm = llm_provider

        for name in self.agent_registry.list_agents():
            agent = self.agent_registry.get(name)
            if agent:
                agent.set_llm(llm_provider)

        self.task_router = TaskRouter(
            {
                "general": self.agent_registry.get("general"),
                "code_companion": self.agent_registry.get("code_companion"),
                "file_ops": self.agent_registry.get("file_ops"),
            }
        )
        logger.info("LLM provider configured")

    async def execute_task(self, task: str) -> str:
        if not self._llm:
            return "LLM not configured. Please set up an LLM provider."

        if not self.task_router:
            agent = self.agent_registry.get("general")
            if agent:
                response = await agent.run(task)
                return response.content
            return "No agents available"

        agent_name = self.task_router.route(task)
        agent = self.agent_registry.get(agent_name)

        if agent:
            response = await agent.run(task)
            return response.content

        return f"No agent found for: {task}"

    def get_tool_schemas(self):
        return self.tool_registry.get_all_schemas()

    def list_agents(self):
        return self.agent_registry.list_agents()

    def list_tools(self):
        return self.tool_registry.list_tools()

    async def execute_tool(self, tool_name: str, **kwargs) -> ToolResult:
        return await self.tool_registry.execute(tool_name, **kwargs)


def get_buddy_core() -> BuddyCore:
    return BuddyCore()
