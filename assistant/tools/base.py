import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    success: bool
    result: Any
    error: str | None = None
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class BaseTool(ABC):
    name: str = "base_tool"
    description: str = "Base tool"
    parameters: dict = {}

    def __init__(self):
        self.logger = logging.getLogger(f"{__name__}.{self.name}")

    @abstractmethod
    async def execute(self, **kwargs) -> ToolResult:
        pass

    def validate_params(self, **kwargs) -> bool:
        required = self.parameters.get("required", [])
        for param in required:
            if param not in kwargs:
                self.logger.error(f"Missing required parameter: {param}")
                return False
        return True

    def get_schema(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }
