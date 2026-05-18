"""
Browser Harness Skill - CDP-based browser automation via browser-harness
"""

import asyncio
import os

from skills.base_skill import BaseSkill, skill

HARNESS_PATH = r"C:\Users\h0093\.claude\skills\browser-harness"
_HARNESS_ENV = {**os.environ, "BU_CDP_WS": "ws://127.0.0.1:9222"}


@skill(
    name="browser_harness",
    description="Direct browser control via CDP using browser-harness. For automation, scraping, and web interaction.",
    keywords=[
        "browser harness",
        "cdp browser",
        "scrape",
        "automate browser",
    ],
)
class BrowserHarnessSkill(BaseSkill):
    _initialized = False

    def __init__(self):
        super().__init__()

    async def _run(self, code: str, timeout: int = 30) -> tuple[int, str, str]:
        proc = await asyncio.create_subprocess_exec(
            "uv",
            "run",
            "browser-harness",
            "-c",
            code,
            cwd=HARNESS_PATH,
            env=_HARNESS_ENV,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout)
            return (
                proc.returncode or 0,
                out.decode(errors="replace"),
                err.decode(errors="replace"),
            )
        except TimeoutError:
            proc.kill()
            return -1, "", "timeout"

    async def handle(self, command: str, context: dict = None) -> str:
        code = command.strip().strip("`").strip()
        rc, stdout, stderr = await self._run(code)
        if rc != 0:
            return f"Error: {stderr[:500]}"
        return stdout

    def get_tool_schemas(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "browser_harness_exec",
                    "description": "Execute browser-harness Python code for CDP browser automation.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "code": {
                                "type": "string",
                                "description": "Python code to execute (e.g., 'goto_url(\"https://example.com\")').",
                            }
                        },
                        "required": ["code"],
                    },
                },
            }
        ]

    async def execute_tool(self, tool_name: str, args: dict) -> str:
        if tool_name == "browser_harness_exec":
            return await self.handle(args.get("code", ""))
        return "Unknown tool"
