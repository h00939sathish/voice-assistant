import re
import secrets
import time
from typing import Any

from assistant.long_term_memory import LongTermMemory, Memory
from skills.base_skill import BaseSkill, skill


@skill(
    name="memory_control",
    keywords=[
        "what do you remember",
        "show memories",
        "list memories",
        "memory stats",
        "search memory",
        "find memory",
        "remember that",
        "save memory",
        "forget memory",
        "delete memory",
        "clear memories",
    ],
    description="Manage long-term memory: list, search, add, delete, and clear with confirmations",
    priority=9,
)
class MemoryControlSkill(BaseSkill):
    """User-facing memory management commands for long-term memory."""

    CONFIRM_TIMEOUT_SECONDS = 60

    def __init__(self):
        super().__init__()
        self.memory = LongTermMemory()
        self._pending_confirmation: dict[str, Any] | None = None

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        text_lower = text.lower().strip()

        if any(
            cancel in text_lower
            for cancel in ["cancel memory action", "cancel action", "never mind"]
        ):
            return self._cancel_pending_action()

        confirmation = self._handle_confirmation(text_lower)
        if confirmation:
            return confirmation

        if self._is_stats_request(text_lower):
            return self._memory_stats()

        if self._is_list_request(text_lower):
            return self._list_recent_memories(text_lower)

        if self._is_search_request(text_lower):
            return self._search_memories(text, text_lower)

        if self._is_correction_request(text_lower):
            return self._correct_memory(text, text_lower)

        if self._is_forget_query_request(text_lower):
            return self._forget_by_query(text, text_lower)

        if self._is_store_request(text_lower):
            return self._store_memory(text, text_lower)

        delete_match = re.search(r"\b(?:forget|delete)\s+memory\s+(\d+)\b", text_lower)
        if delete_match:
            memory_id = int(delete_match.group(1))
            return self._request_delete(memory_id)

        if re.search(r"\b(?:clear|wipe)\s+(?:all\s+)?memories\b", text_lower):
            return self._request_clear_all()

        return (
            "Memory controls: 'what do you remember', 'memory stats', "
            "'search memory <query>', 'remember that <fact>', "
            "'forget memory <id>', or 'clear memories'."
        )

    def _is_stats_request(self, text_lower: str) -> bool:
        return any(
            phrase in text_lower
            for phrase in [
                "memory stats",
                "memory status",
                "how many memories",
                "memory summary",
            ]
        )

    def _is_list_request(self, text_lower: str) -> bool:
        return any(
            phrase in text_lower
            for phrase in [
                "what do you remember",
                "show memories",
                "list memories",
                "recent memories",
            ]
        )

    def _is_search_request(self, text_lower: str) -> bool:
        return "search memory" in text_lower or "find memory" in text_lower

    def _is_store_request(self, text_lower: str) -> bool:
        return (
            "remember that" in text_lower
            or "save memory" in text_lower
            or text_lower.startswith("remember ")
        )

    def _is_correction_request(self, text_lower: str) -> bool:
        return "remember this instead" in text_lower

    def _is_forget_query_request(self, text_lower: str) -> bool:
        return text_lower.startswith("forget this ") and "memory " not in text_lower

    def _memory_stats(self) -> str:
        stats = self.memory.get_stats()
        if not stats:
            return "I couldn't read memory statistics right now."

        total = stats.get("total_memories", 0)
        avg = stats.get("average_confidence", 0.0)
        by_category = stats.get("by_category", {})
        top_categories = sorted(by_category.items(), key=lambda x: x[1], reverse=True)[
            :5
        ]
        categories = (
            ", ".join(f"{name}:{count}" for name, count in top_categories) or "none"
        )
        return f"Memory stats: total={total}, average confidence={avg}, top categories: {categories}."

    def _list_recent_memories(self, text_lower: str) -> str:
        limit = self._extract_limit(text_lower, default_limit=5, max_limit=20)
        memories = self.memory.get_recent(limit=limit, min_confidence=0.2)
        if not memories:
            return "I don't have any long-term memories yet."

        lines = ["Recent memories:"]
        for mem in memories:
            lines.append(self._format_memory_line(mem))
        return "\n".join(lines)

    def _search_memories(self, text: str, text_lower: str) -> str:
        query = ""
        for marker in ["search memory", "find memory"]:
            idx = text_lower.find(marker)
            if idx >= 0:
                query = text[idx + len(marker) :].strip(" :.-")
                break

        if not query:
            return "Please provide a memory query, for example: 'search memory my project deadline'."

        limit = self._extract_limit(text_lower, default_limit=5, max_limit=20)
        memories = self.memory.search(query=query, limit=limit, min_confidence=0.2)
        if not memories:
            return f"I couldn't find matching memories for '{query}'."

        lines = [f"Memory search results for '{query}':"]
        for mem in memories:
            lines.append(self._format_memory_line(mem))
        return "\n".join(lines)

    def _store_memory(self, text: str, text_lower: str) -> str:
        content = self._extract_memory_content(text, text_lower)
        if not content:
            return "Tell me what to remember, for example: 'remember that I prefer dark roast coffee'."

        category = self._infer_category(content.lower())
        memory_id = self.memory.remember_this(content=content, category=category)
        if memory_id < 0:
            return "I couldn't save that memory due to a storage error."

        return f"Saved memory #{memory_id} in category '{category}'."

    def _correct_memory(self, text: str, text_lower: str) -> str:
        pattern = re.search(
            r"remember this instead\s+(.+?)\s+instead of\s+(.+)", text, re.IGNORECASE
        )
        if not pattern:
            return (
                "Use: 'remember this instead <new fact> instead of <old fact>'. "
                "Example: remember this instead my favorite color is blue instead of favorite color is red."
            )

        new_fact = pattern.group(1).strip(" .")
        old_fact = pattern.group(2).strip(" .")
        if not new_fact or not old_fact:
            return "I need both the new fact and the old fact to apply a correction."

        ok = self.memory.correct_this(old_fact, new_fact)
        if not ok:
            return "I couldn't apply that correction."
        return f"Updated memory: replaced '{old_fact}' with '{new_fact}'."

    def _forget_by_query(self, text: str, text_lower: str) -> str:
        query = text[len("forget this ") :].strip(" .")
        if not query:
            return "Tell me what to forget, for example: 'forget this favorite color is red'."

        count = self.memory.forget_this(query)
        if count <= 0:
            return f"I could not find matching memories for '{query}'."
        return f"Forgot {count} memory item(s) matching '{query}'."

    def _request_delete(self, memory_id: int) -> str:
        target = self.memory.get_by_id(memory_id)
        if not target:
            return f"I couldn't find memory #{memory_id}."

        token = f"{secrets.randbelow(9000) + 1000}"
        self._pending_confirmation = {
            "type": "delete",
            "memory_id": memory_id,
            "token": token,
            "expires_at": time.time() + self.CONFIRM_TIMEOUT_SECONDS,
        }
        snippet = target.content[:70].strip()
        return (
            f"Safety check: memory #{memory_id} ('{snippet}') will be deleted. "
            f"Say 'confirm delete memory {memory_id} {token}' within "
            f"{self.CONFIRM_TIMEOUT_SECONDS} seconds, or 'cancel memory action'."
        )

    def _request_clear_all(self) -> str:
        token = f"{secrets.randbelow(9000) + 1000}"
        self._pending_confirmation = {
            "type": "clear_all",
            "token": token,
            "expires_at": time.time() + self.CONFIRM_TIMEOUT_SECONDS,
        }
        return (
            "Safety check: this will erase all long-term memories. "
            f"Say 'confirm clear memories {token}' within {self.CONFIRM_TIMEOUT_SECONDS} seconds, "
            "or 'cancel memory action'."
        )

    def _cancel_pending_action(self) -> str:
        if not self._pending_confirmation:
            return "There is no pending memory action to cancel."
        action = self._pending_confirmation["type"]
        self._pending_confirmation = None
        return f"Cancelled pending memory action: {action}."

    def _handle_confirmation(self, text_lower: str) -> str | None:
        if "confirm" not in text_lower:
            return None
        if not self._pending_confirmation:
            return "There is no pending memory action to confirm."
        if time.time() > float(self._pending_confirmation["expires_at"]):
            action = self._pending_confirmation["type"]
            self._pending_confirmation = None
            return f"Pending memory action '{action}' expired. Please request it again."

        action_type = self._pending_confirmation["type"]
        token = self._pending_confirmation["token"]
        if action_type == "delete":
            memory_id = self._pending_confirmation["memory_id"]
            expected = f"confirm delete memory {memory_id} {token}"
            if expected not in text_lower:
                return f"Confirmation mismatch. Say exactly: '{expected}'."
            self.memory.delete(memory_id)
            self._pending_confirmation = None
            return f"Deleted memory #{memory_id}."

        if action_type == "clear_all":
            expected = f"confirm clear memories {token}"
            if expected not in text_lower:
                return f"Confirmation mismatch. Say exactly: '{expected}'."
            self.memory.clear()
            self._pending_confirmation = None
            return "All long-term memories were cleared."

        return "Unknown pending memory action."

    def _extract_limit(
        self, text_lower: str, default_limit: int, max_limit: int
    ) -> int:
        match = re.search(r"\b(\d{1,2})\b", text_lower)
        if not match:
            return default_limit
        return max(1, min(max_limit, int(match.group(1))))

    def _extract_memory_content(self, text: str, text_lower: str) -> str:
        markers = ["remember that", "save memory", "remember "]
        for marker in markers:
            idx = text_lower.find(marker)
            if idx >= 0:
                content = text[idx + len(marker) :].strip(" :.-")
                return content
        return ""

    def _infer_category(self, content_lower: str) -> str:
        if any(
            p in content_lower for p in ["i like", "i prefer", "favorite", "favourite"]
        ):
            return "preference"
        if any(p in content_lower for p in ["my name is", "i live", "i work", "i am "]):
            return "profile"
        if any(
            p in content_lower
            for p in ["wife", "husband", "partner", "dog", "cat", "boss", "friend"]
        ):
            return "relationship"
        if any(p in content_lower for p in ["usually", "every day", "daily", "often"]):
            return "task"
        if any(p in content_lower for p in ["goal", "plan", "want to"]):
            return "goal"
        return "profile"

    def _format_memory_line(self, mem: Memory) -> str:
        conf = mem.confidence if mem.confidence is not None else 0.0
        return f"- #{mem.id} [{mem.category}] ({conf:.2f}) {mem.content}"
