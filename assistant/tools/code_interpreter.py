import io
import subprocess
import sys
import traceback

from .base import BaseTool, ToolResult

SAFE_BUILTINS = {
    "print": print,
    "len": len,
    "str": str,
    "int": int,
    "float": float,
    "bool": bool,
    "list": list,
    "dict": dict,
    "tuple": tuple,
    "set": set,
    "range": range,
    "enumerate": enumerate,
    "zip": zip,
    "map": map,
    "filter": filter,
    "sum": sum,
    "min": min,
    "max": max,
    "abs": abs,
    "round": round,
    "sorted": sorted,
    "reversed": reversed,
    "any": any,
    "all": all,
    "isinstance": isinstance,
    "type": type,
    "hasattr": hasattr,
    "getattr": getattr,
    "setattr": setattr,
    "input": None,
    "open": None,
    "exec": None,
    "eval": None,
    "__import__": None,
    "exit": None,
    "quit": None,
}


class SafeGlobals:
    pass


def create_sandbox():
    sandbox = SafeGlobals()
    for name, func in SAFE_BUILTINS.items():
        setattr(sandbox, name, func)
    return sandbox


class CodeInterpreterTool(BaseTool):
    name = "code_exec"
    description = "Execute Python code and return output"
    parameters = {
        "type": "object",
        "properties": {
            "code": {"type": "string", "description": "Python code to execute"},
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds",
                "default": 30,
            },
            "globals": {
                "type": "object",
                "description": "Optional globals to pass",
                "default": {},
            },
        },
        "required": ["code"],
    }

    async def execute(
        self, code: str, timeout: int = 30, globals: dict | None = None, **kwargs
    ) -> ToolResult:
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        stdout_capture = io.StringIO()
        stderr_capture = io.StringIO()

        local_vars = {}
        if globals:
            local_vars.update(globals)

        try:
            sys.stdout = stdout_capture
            sys.stderr = stderr_capture

            try:
                sandbox = create_sandbox()
                exec(code, sandbox.__dict__, local_vars)
                output = stdout_capture.getvalue()
                if stderr_capture.getvalue():
                    output += "\n[stderr]: " + stderr_capture.getvalue()
            except Exception as e:
                output = stdout_capture.getvalue()
                output += f"\nError: {str(e)}\n"
                output += traceback.format_exc()

            return ToolResult(
                success=True, result=output or "Code executed successfully (no output)"
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False,
                result=None,
                error=f"Code execution timed out after {timeout}s",
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))
        finally:
            sys.stdout = old_stdout
            sys.stderr = old_stderr


class BashRunnerTool(BaseTool):
    name = "bash"
    description = "Execute bash/shell script"
    parameters = {
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "Bash script to execute"},
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds",
                "default": 30,
            },
        },
        "required": ["script"],
    }

    async def execute(self, script: str, timeout: int = 30, **kwargs) -> ToolResult:
        try:
            result = subprocess.run(
                ["bash", "-c", script], capture_output=True, text=True, timeout=timeout
            )

            output = result.stdout if result.stdout else result.stderr
            return ToolResult(
                success=result.returncode == 0,
                result=output,
                metadata={"returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, result=None, error=f"Script timed out after {timeout}s"
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class PowerShellTool(BaseTool):
    name = "powershell"
    description = "Execute PowerShell script"
    parameters = {
        "type": "object",
        "properties": {
            "script": {"type": "string", "description": "PowerShell script to execute"},
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds",
                "default": 30,
            },
        },
        "required": ["script"],
    }

    async def execute(self, script: str, timeout: int = 30, **kwargs) -> ToolResult:
        try:
            result = subprocess.run(
                ["powershell", "-Command", script],
                capture_output=True,
                text=True,
                timeout=timeout,
            )

            output = result.stdout if result.stdout else result.stderr
            return ToolResult(
                success=result.returncode == 0,
                result=output,
                metadata={"returncode": result.returncode},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, result=None, error=f"Script timed out after {timeout}s"
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))
