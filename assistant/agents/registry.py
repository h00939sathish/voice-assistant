import logging

from .base import BaseAgent

logger = logging.getLogger(__name__)


class AgentRegistry:
    _instance = None
    _agents: dict[str, type[BaseAgent]] = {}
    _instances: dict[str, BaseAgent] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(cls, name: str, agent_class: type[BaseAgent]):
        cls._agents[name] = agent_class
        logger.info(f"Registered agent: {name}")

    @classmethod
    def get(cls, name: str, **kwargs) -> BaseAgent | None:
        if name in cls._instances:
            return cls._instances[name]

        if name in cls._agents:
            instance = cls._agents[name](**kwargs)
            cls._instances[name] = instance
            return instance

        logger.warning(f"Agent not found: {name}")
        return None

    @classmethod
    def list_agents(cls) -> list[str]:
        return list(cls._agents.keys())

    @classmethod
    def create_all(cls, **kwargs) -> dict[str, BaseAgent]:
        created = {}
        for name, agent_class in cls._agents.items():
            try:
                instance = agent_class(**kwargs)
                cls._instances[name] = instance
                created[name] = instance
            except Exception as e:
                logger.error(f"Failed to create agent {name}: {e}")
        return created


def register_agent(name: str):
    def decorator(cls: type[BaseAgent]):
        AgentRegistry.register(name, cls)
        return cls

    return decorator
