import logging
import re

logger = logging.getLogger(__name__)


class TaskRouter:
    """
    Routes user requests to the appropriate agent based on intent detection.
    """

    AGENT_PATTERNS = {
        "code_companion": [
            r"write.*code",
            r"create.*function",
            r"debug",
            r"fix.*error",
            r"refactor",
            r"add.*test",
            r"code.*review",
            r"implement",
            r"\.py$",
            r"\.js$",
            r"\.ts$",
            r"programming",
            r"create.*file.*\.py",
            r"write.*script",
        ],
        "research": [
            r"research",
            r"find.*information",
            r"look.*up",
            r"what.*is.*",
            r"explain",
            r"how.*does",
            r"why.*does",
            r"learn.*about",
            r"history",
            r"summarize",
            r"analyze",
        ],
        "morning_digest": [
            r"morning.*digest",
            r"daily.*briefing",
            r"what.*today",
            r"my.*schedule",
            r"my.*emails",
            r"weather.*today",
            r"good morning",
            r"morning report",
        ],
        "file_ops": [
            r"list.*files",
            r"find.*file",
            r"read.*file",
            r"write.*file",
            r"create.*folder",
            r"delete.*file",
            r"search.*in",
            r"show.*directory",
            r"what.*in.*folder",
        ],
        "general": [],
    }

    def __init__(self, agents: dict):
        self.agents = agents

    def route(self, task: str) -> str:
        task_lower = task.lower()

        scores = {}
        for agent_name, patterns in self.AGENT_PATTERNS.items():
            if agent_name == "general":
                continue
            score = 0
            for pattern in patterns:
                if re.search(pattern, task_lower):
                    score += 1
            scores[agent_name] = score

        if not scores or max(scores.values()) == 0:
            return "general"

        best_agent = max(scores, key=scores.get)
        logger.info(
            f"Routing '{task[:50]}...' to {best_agent} (score: {scores[best_agent]})"
        )

        return best_agent

    def get_agent(self, task: str):
        agent_name = self.route(task)
        return self.agents.get(agent_name, self.agents.get("general"))
