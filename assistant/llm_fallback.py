"""
LLM Fallback - Fallback logic and provider priority management
"""

from typing import List, Dict, Any, Callable, Optional


class FallbackConfig:
    """Configuration for provider fallback behavior"""

    LATENCY_PROFILES = {"fast": 0, "balanced": 1, "slow": 2}
    REASONING_PROFILES = {"high": 0, "medium": 1, "low": 2}

    def __init__(self, prefer_local: bool = True):
        self.prefer_local = prefer_local

    def compute_priority(self, provider_cfg: dict, intent: str) -> tuple[int, int, int]:
        latency_rank = self.LATENCY_PROFILES.get(
            provider_cfg.get("latency_profile", "balanced"), 1
        )
        reasoning_rank = self.REASONING_PROFILES.get(
            provider_cfg.get("reasoning_strength", "medium"), 1
        )
        local_rank = 0 if (self.prefer_local and provider_cfg.get("local")) else 1

        if intent == "fast":
            return (latency_rank, local_rank, reasoning_rank)
        else:
            return (reasoning_rank, latency_rank, local_rank)

    def sort_providers(self, providers: List[dict], intent: str) -> List[tuple]:
        sorted_providers = sorted(
            providers, key=lambda p: self.compute_priority(p, intent)
        )
        return [
            (p["name"], p["handler"], bool(p["available"])) for p in sorted_providers
        ]


class FallbackChain:
    """Manages fallback chain between providers"""

    def __init__(self, config: FallbackConfig):
        self.config = config
        self._all_providers_failed = False

    def mark_all_failed(self):
        self._all_providers_failed = True

    def reset(self):
        self._all_providers_failed = False

    def should_fallback(self, response: Optional[str]) -> bool:
        return response is None

    def get_error_response(self) -> str:
        return "All my brain connections are down. Please check your internet and API keys."


def create_provider_priority_list(
    providers: List[Dict[str, Any]], intent: str, prefer_local: bool = True
) -> List[tuple]:
    """Create sorted provider priority queue based on intent and preferences"""
    config = FallbackConfig(prefer_local)
    return config.sort_providers(providers, intent)


def determine_intent(text: str) -> str:
    """Classify user request complexity for provider selection"""
    complex_keywords = [
        "and",
        "then",
        "also",
        "explain",
        "why",
        "how",
        "research",
        "search",
        "find",
        "create",
        "write",
        "analyze",
    ]
    action_verbs = [
        "open",
        "run",
        "delete",
        "create",
        "execute",
        "launch",
    ]
    text_lower = text.lower()
    words = text_lower.split()
    if (
        any(w in words for w in complex_keywords)
        or len(text.split()) > 8
        or any(w in words for w in action_verbs)
    ):
        return "complex"
    return "fast"
