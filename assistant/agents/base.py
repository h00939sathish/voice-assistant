from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentState(Enum):
    IDLE = "idle"
    THINKING = "thinking"
    ACTING = "acting"
    FINALIZING = "finalizing"
    ERROR = "error"


@dataclass
class AgentContext:
    task: str
    history: list = field(default_factory=list)
    tools_used: list = field(default_factory=list)
    metadata: dict = field(default_factory=dict)


@dataclass
class AgentResponse:
    content: str
    tool_calls: list = field(default_factory=list)
    state: AgentState = AgentState.IDLE
    metadata: dict = field(default_factory=dict)


class BaseAgent(ABC):
    name: str = "base"
    description: str = "Base agent"
    tools: list = field(default_factory=list)

    def __init__(self, llm=None):
        self.llm = llm
        self.state = AgentState.IDLE
        self.context: AgentContext | None = None

    @abstractmethod
    async def run(
        self, task: str, context: AgentContext | None = None
    ) -> AgentResponse:
        pass

    @abstractmethod
    async def execute_tool(self, tool_name: str, args: dict) -> Any:
        pass

    def set_llm(self, llm):
        self.llm = llm

    async def think(self, prompt: str) -> str:
        if self.llm:
            return await self.llm.complete(prompt)
        return "LLM not configured"

    def get_tools_schema(self) -> list:
        return [
            {"name": t["name"], "description": t["description"]} for t in self.tools
        ]
