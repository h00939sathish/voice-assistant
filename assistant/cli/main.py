import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.core import get_buddy_core


class SimpleLLM:
    """Simple LLM wrapper that uses existing Ollama integration."""

    def __init__(self, model: str = "qwen3.5:4b-q4_K_M"):
        self.model = model
        self._ollama = None

    def _get_ollama(self):
        if self._ollama is None:
            import ollama

            self._ollama = ollama
        return self._ollama

    async def complete(self, prompt: str) -> str:
        try:
            ollama = self._get_ollama()
            response = ollama.chat(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.7},
            )
            return response.message.content
        except Exception as e:
            return f"LLM Error: {str(e)}"


async def main():
    if len(sys.argv) < 2:
        print("Usage: python -m assistant.cli <task>")
        print("\nExamples:")
        print("  python -m assistant.cli 'list files in Documents'")
        print("  python -m assistant.cli 'read file config.py'")
        print("  python -m assistant.cli 'what is the weather today'")
        print("  python -m assistant.cli 'create a hello world python file'")
        return

    task = " ".join(sys.argv[1:])

    print(f"🤖 Buddy: Processing: {task}\n")

    core = get_buddy_core()
    llm = SimpleLLM()
    core.set_llm(llm)

    print(f"📋 Available tools: {', '.join(core.list_tools())}")
    print(f"🤖 Available agents: {', '.join(core.list_agents())}\n")

    result = await core.execute_task(task)
    print(f"\n✅ Result:\n{result}")


if __name__ == "__main__":
    asyncio.run(main())
