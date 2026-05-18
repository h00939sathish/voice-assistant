"""
Dependency Injection Container - Manages and resolves assistant components.
Follows the Singleton pattern for global access.
"""

import logging
from collections.abc import Callable
from typing import Any

from assistant.events import EventBus

logger = logging.getLogger(__name__)


class Container:
    """
    Inversion of Control (IoC) Container for Dependency Injection.
    Maps interfaces (abstract classes) to concrete implementations.
    """

    _instance = None
    _registry: dict[type, Any] = {}
    _singleton_map: dict[type, Any] = {}
    _factory_map: dict[type, Callable[[], Any]] = {}

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    @classmethod
    def register(
        cls, interface: type, implementation: type | Any, is_singleton: bool = True
    ):
        """Register a concrete implementation for an interface."""
        if not isinstance(implementation, type) and not callable(implementation):
            # Already instantiated singleton
            cls._singleton_map[interface] = implementation
            logger.debug(f"Registered singleton instance for {interface.__name__}")
        elif is_singleton:
            cls._registry[interface] = implementation
            logger.debug(f"Registered singleton type for {interface.__name__}")
        else:
            cls._factory_map[interface] = implementation
            logger.debug(f"Registered factory type for {interface.__name__}")

    @classmethod
    def resolve(cls, interface: type) -> Any:
        """Resolve and return an implementation for the given interface."""
        # 1. Check for existing singleton instance
        if interface in cls._singleton_map:
            return cls._singleton_map[interface]

        # 2. Check for registered singleton type
        if interface in cls._registry:
            implementation_type = cls._registry[interface]
            instance = implementation_type()
            cls._singleton_map[interface] = instance  # Cache it
            return instance

        # 3. Check for factory type (new instance every time)
        if interface in cls._factory_map:
            factory = cls._factory_map[interface]
            return factory()

        raise ValueError(f"No implementation registered for {interface.__name__}")

    @classmethod
    def clear(cls):
        """Clear all registrations (mainly for testing)."""
        cls._registry.clear()
        cls._singleton_map.clear()
        cls._factory_map.clear()


# Global container instance
container = Container()

# Register default instances
from assistant.events import bus

container.register(EventBus, bus)
