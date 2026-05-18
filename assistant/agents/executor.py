import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class LoopState(Enum):
    THINKING = "thinking"
    ACTING = "acting"
    OBSERVATION = "observation"
    FINAL = "final"
    ERROR = "error"


@dataclass
class ToolCall:
    name: str
    arguments: dict[str, Any]
    result: str | None = None
    error: str | None = None


@dataclass
class ReActStep:
    thought: str = ""
    action: str | None = None
    action_input: dict[str, Any] = field(default_factory=dict)
    observation: str = ""
    state: LoopState = LoopState.THINKING


class ReActExecutor:
    """
    ReAct (Reason + Act) loop executor for task completion.
    Iterates: Thought → Action → Observation → Thought → ... → Final Answer
    """

    def __init__(self, llm_provider, tool_registry, max_iterations: int = 10):
        self.llm = llm_provider
        self.tools = tool_registry
        self.max_iterations = max_iterations
        self.history: list[ReActStep] = []

        self.system_prompt = """You are Buddy, a helpful AI assistant with access to tools.

Follow this loop:
1. THOUGHT: Analyze the task and decide what to do
2. ACTION: Choose a tool to use (if needed)
3. OBSERVATION: See the result of your action
4. REPEAT until you have the answer
5. FINAL: Provide your final answer

Available tools:
{tools}

Respond in this format:
THOUGHT: <your thinking>
ACTION: <tool_name> | <arguments as JSON>
OBSERVATION: <result from tool or N/A if final>

If no more tools needed:
THOUGHT: <your final thinking>
ACTION: FINAL
OBSERVATION: N/A"""

    def get_tools_description(self) -> str:
        schemas = self.tools.get_all_schemas()
        lines = []
        for s in schemas:
            lines.append(f"- {s['name']}: {s['description']}")
        return "\n".join(lines)

    async def execute(self, task: str) -> str:
        self.history = []
        context = task

        for i in range(self.max_iterations):
            prompt = self._build_prompt(context)
            response = await self.llm.complete(prompt)

            step = self._parse_response(response)
            self.history.append(step)

            if step.state == LoopState.FINAL:
                return step.thought.replace("FINAL: ", "").strip()

            if step.action:
                result = await self._execute_tool(step.action, step.action_input)
                step.observation = result
                context += f"\n\nObservation: {result}"

            logger.info(f"ReAct iteration {i + 1}: {step.state.value}")

        return "I couldn't complete this task within the maximum iterations."

    def _build_prompt(self, context: str) -> str:
        tools_desc = self.get_tools_description()

        history_text = ""
        if self.history:
            lines = ["Previous steps:"]
            for step in self.history:
                lines.append(f"THOUGHT: {step.thought}")
                if step.action:
                    lines.append(f"ACTION: {step.action}")
                    lines.append(f"OBSERVATION: {step.observation}")
            history_text = "\n".join(lines) + "\n\n"

        return f"""{self.system_prompt.format(tools=tools_desc)}

{history_text}

Task: {context}

Your response:"""

    def _parse_response(self, response: str) -> ReActStep:
        step = ReActStep()

        lines = response.strip().split("\n")
        for line in lines:
            line = line.strip()
            if line.startswith("THOUGHT:"):
                step.thought = line[8:].strip()
            elif line.startswith("ACTION:"):
                action_part = line[7:].strip()
                if action_part == "FINAL":
                    step.state = LoopState.FINAL
                else:
                    if "|" in action_part:
                        parts = action_part.split("|", 1)
                        step.action = parts[0].strip()
                        if len(parts) > 1:
                            import json

                            try:
                                step.action_input = json.loads(parts[1].strip())
                            except Exception:
                                step.action_input = {"input": parts[1].strip()}
                    else:
                        step.action = action_part
            elif line.startswith("OBSERVATION:"):
                step.observation = line[12:].strip()

        if not step.action:
            step.state = LoopState.FINAL

        return step

    async def _execute_tool(self, tool_name: str, args: dict) -> str:
        result = await self.tools.execute(tool_name, **args)

        if result.success:
            return str(result.result)
        else:
            return f"Error: {result.error}"

    def get_history(self) -> list[dict]:
        return [
            {"thought": s.thought, "action": s.action, "observation": s.observation}
            for s in self.history
        ]
