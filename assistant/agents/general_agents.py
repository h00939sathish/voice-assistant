import logging

from .base import AgentContext, AgentResponse, AgentState, BaseAgent
from .executor import ReActExecutor
from .registry import register_agent

logger = logging.getLogger(__name__)


@register_agent("general")
class GeneralAgent(BaseAgent):
    name = "general"
    description = "General purpose agent for any task"

    def __init__(self, llm=None, tool_registry=None):
        super().__init__(llm)
        self.tools = tool_registry
        self.executor = (
            ReActExecutor(llm, tool_registry) if llm and tool_registry else None
        )

    async def run(
        self, task: str, context: AgentContext | None = None
    ) -> AgentResponse:
        if not self.executor:
            return AgentResponse(
                content="LLM not configured. Please set up the LLM provider.",
                state=AgentState.ERROR,
            )

        try:
            result = await self.executor.execute(task)
            return AgentResponse(content=result, state=AgentState.FINAL)
        except Exception as e:
            logger.error(f"General agent error: {e}")
            return AgentResponse(content=f"Error: {str(e)}", state=AgentState.ERROR)

    async def execute_tool(self, tool_name: str, args: dict):
        if self.tools:
            return await self.tools.execute(tool_name, **args)
        return None


@register_agent("code_companion")
class CodeCompanionAgent(BaseAgent):
    name = "code_companion"
    description = "Agent for code-related tasks (write, debug, review)"

    def __init__(self, llm=None, tool_registry=None):
        super().__init__(llm)
        self.tools = tool_registry
        self.executor = (
            ReActExecutor(llm, tool_registry) if llm and tool_registry else None
        )

    async def run(
        self, task: str, context: AgentContext | None = None
    ) -> AgentResponse:
        if not self.executor:
            return AgentResponse(content="LLM not configured", state=AgentState.ERROR)

        task_with_context = f"""You are a code assistant. Help with:
- Writing code
- Debugging errors
- Code review
- Creating tests

Task: {task}"""

        result = await self.executor.execute(task_with_context)
        return AgentResponse(content=result, state=AgentState.FINAL)

    async def execute_tool(self, tool_name: str, args: dict):
        if self.tools:
            return await self.tools.execute(tool_name, **args)


@register_agent("file_ops")
class FileOpsAgent(BaseAgent):
    name = "file_ops"
    description = "Agent for file operations (read, write, list, search)"

    def __init__(self, llm=None, tool_registry=None):
        super().__init__(llm)
        self.tools = tool_registry

    async def run(
        self, task: str, context: AgentContext | None = None
    ) -> AgentResponse:
        if not self.tools:
            return AgentResponse(content="Tools not configured", state=AgentState.ERROR)

        task_lower = task.lower()

        if "list" in task_lower or "show" in task_lower:
            parts = task.split()
            path = "."
            for i, w in enumerate(parts):
                if w in ["in", "at", "folder", "directory"] and i + 1 < len(parts):
                    path = parts[i + 1]
                    break

            result = await self.tools.execute("file_list", path=path)
            return AgentResponse(
                content=f"Files in {path}:\n{result.result}", state=AgentState.FINAL
            )

        if "read" in task_lower:
            parts = task.split()
            path = None
            for i, w in enumerate(parts):
                if w in ["file", "the"] and i + 1 < len(parts):
                    path = parts[i + 1]
                    break

            if path:
                result = await self.tools.execute("file_read", path=path)
                return AgentResponse(
                    content=result.result or f"Error: {result.error}",
                    state=AgentState.FINAL,
                )

        return AgentResponse(
            content="I can help with: listing files, reading files, searching files. Try 'list files in Documents'",
            state=AgentState.FINAL,
        )

    async def execute_tool(self, tool_name: str, args: dict):
        if self.tools:
            return await self.tools.execute(tool_name, **args)
