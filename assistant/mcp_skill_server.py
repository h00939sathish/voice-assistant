"""
MCP Skill Server — lightweight JSON-lines server for out-of-process skills.

Each heavy skill runs this as __main__:

    if __name__ == "__main__":
        from assistant.mcp_skill_server import run_skill_server
        run_skill_server(MyHeavySkill())

Protocol (stdin → stdout, one JSON per line):
    Request:  {"id": 1, "text": "user query", "context": {}}
    Response: {"id": 1, "result": "skill response"}
    Error:    {"id": 1, "error": "message"}
"""

import asyncio
import json
import sys
import traceback
from typing import Any


def run_skill_server(skill_instance: Any) -> None:
    """Blocking entry point — run in __main__ of a skill file."""
    asyncio.run(_serve(skill_instance))


async def _serve(skill_instance: Any) -> None:
    """Read JSON requests from stdin, write JSON responses to stdout."""
    loop = asyncio.get_event_loop()
    reader = asyncio.StreamReader()
    protocol = asyncio.StreamReaderProtocol(reader)
    await loop.connect_read_pipe(lambda: protocol, sys.stdin)

    writer_transport, writer_protocol = await loop.connect_write_pipe(
        asyncio.BaseProtocol, sys.stdout.buffer
    )
    writer = asyncio.StreamWriter(writer_transport, writer_protocol, reader, loop)

    while True:
        try:
            line = await reader.readline()
            if not line:
                break  # stdin closed — parent process ended

            request = json.loads(line.decode())
            req_id = request.get("id", 0)
            text = request.get("text", "")
            context = request.get("context", {})

            try:
                result = await skill_instance.handle(text, context)
                # SkillResponse → extract text
                if hasattr(result, "text"):
                    result = result.text
                response = {"id": req_id, "result": str(result)}
            except Exception as e:
                response = {
                    "id": req_id,
                    "error": str(e),
                    "trace": traceback.format_exc(),
                }

            line_out = (json.dumps(response) + "\n").encode()
            writer.write(line_out)
            await writer.drain()

        except json.JSONDecodeError as e:
            err = json.dumps({"id": -1, "error": f"JSON decode: {e}"}) + "\n"
            writer.write(err.encode())
            await writer.drain()
        except Exception:
            # Fatal — exit so the loader can detect the crash and restart
            break
