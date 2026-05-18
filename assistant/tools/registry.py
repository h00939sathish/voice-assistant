import logging

from .base import BaseTool, ToolResult

logger = logging.getLogger(__name__)


class ToolRegistry:
    _instance = None
    _tools: dict[str, BaseTool] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def register(self, tool: BaseTool):
        self._tools[tool.name] = tool
        logger.info(f"Registered tool: {tool.name}")

    def get(self, name: str) -> BaseTool | None:
        return self._tools.get(name)

    def list_tools(self) -> list[str]:
        return list(self._tools.keys())

    def get_all_schemas(self) -> list[dict]:
        return [tool.get_schema() for tool in self._tools.values()]

    async def execute(self, tool_name: str, **kwargs) -> ToolResult:
        tool = self.get(tool_name)
        if not tool:
            return ToolResult(
                success=False, result=None, error=f"Tool not found: {tool_name}"
            )

        try:
            return await tool.execute(**kwargs)
        except Exception as e:
            logger.error(f"Tool {tool_name} failed: {e}")
            return ToolResult(success=False, result=None, error=str(e))


def get_tool_registry() -> ToolRegistry:
    return ToolRegistry()
