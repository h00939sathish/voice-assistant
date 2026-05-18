"""
LLM Cache - Response caching layer for LLM providers
"""

import hashlib
import time
from typing import Any


class LLMResponseCache:
    """Simple in-memory cache for LLM responses"""

    def __init__(self, ttl_seconds: int = 300):
        self._cache: dict[str, dict[str, Any]] = {}
        self._ttl = ttl_seconds

    def _make_key(self, user_message: str, history_hash: str | None = None) -> str:
        base = f"{user_message}:{history_hash or ''}"
        return hashlib.md5(base.encode()).hexdigest()

    def get(self, user_message: str, history_hash: str | None = None) -> str | None:
        key = self._make_key(user_message, history_hash)
        entry = self._cache.get(key)
        if entry and (time.time() - entry["timestamp"] < self._ttl):
            return entry["response"]
        return None

    def set(self, user_message: str, response: str, history_hash: str | None = None):
        key = self._make_key(user_message, history_hash)
        self._cache[key] = {"response": response, "timestamp": time.time()}

    def clear(self):
        self._cache.clear()

    def invalidate(self, user_message: str, history_hash: str | None = None):
        key = self._make_key(user_message, history_hash)
        self._cache.pop(key, None)
