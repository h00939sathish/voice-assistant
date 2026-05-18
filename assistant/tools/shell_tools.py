import os
import shutil
import subprocess

from .base import BaseTool, ToolResult


class ShellExecTool(BaseTool):
    name = "shell_exec"
    description = "Execute a shell command and return output"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Command to execute"},
            "timeout": {
                "type": "integer",
                "description": "Timeout in seconds",
                "default": 30,
            },
            "cwd": {"type": "string", "description": "Working directory"},
        },
        "required": ["command"],
    }

    DANGEROUS_COMMANDS = ["rm -rf", "del /", "format", "dd if="]

    async def execute(
        self, command: str, timeout: int = 30, cwd: str | None = None, **kwargs
    ) -> ToolResult:
        try:
            for danger in self.DANGEROUS_COMMANDS:
                if danger in command.lower():
                    return ToolResult(
                        success=False,
                        result=None,
                        error=f"Dangerous command blocked: {danger}",
                    )

            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=cwd or os.getcwd(),
            )

            output = result.stdout if result.stdout else result.stderr
            return ToolResult(
                success=result.returncode == 0,
                result=output,
                metadata={"returncode": result.returncode, "command": command},
            )
        except subprocess.TimeoutExpired:
            return ToolResult(
                success=False, result=None, error=f"Command timed out after {timeout}s"
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class GitTool(BaseTool):
    name = "git"
    description = "Execute git commands"
    parameters = {
        "type": "object",
        "properties": {
            "command": {"type": "string", "description": "Git command (without 'git')"},
            "repo_path": {"type": "string", "description": "Repository path"},
        },
        "required": ["command"],
    }

    async def execute(
        self, command: str, repo_path: str | None = None, **kwargs
    ) -> ToolResult:
        try:
            full_cmd = f"git {command}"
            result = subprocess.run(
                full_cmd,
                shell=True,
                capture_output=True,
                text=True,
                timeout=30,
                cwd=repo_path or os.getcwd(),
            )

            output = result.stdout if result.stdout else result.stderr
            return ToolResult(
                success=result.returncode == 0,
                result=output,
                metadata={"returncode": result.returncode},
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class WhichTool(BaseTool):
    name = "which"
    description = "Find executable in PATH"
    parameters = {
        "type": "object",
        "properties": {"program": {"type": "string", "description": "Program name"}},
        "required": ["program"],
    }

    async def execute(self, program: str, **kwargs) -> ToolResult:
        try:
            path = shutil.which(program)
            return ToolResult(success=path is not None, result=path)
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class PwdTool(BaseTool):
    name = "pwd"
    description = "Get current working directory"
    parameters = {"type": "object", "properties": {}}

    async def execute(self, **kwargs) -> ToolResult:
        return ToolResult(success=True, result=os.getcwd())


class EnvTool(BaseTool):
    name = "env"
    description = "Get environment variables"
    parameters = {
        "type": "object",
        "properties": {
            "key": {"type": "string", "description": "Variable name (optional)"}
        },
    }

    async def execute(self, key: str | None = None, **kwargs) -> ToolResult:
        try:
            if key:
                value = os.environ.get(key)
                return ToolResult(success=value is not None, result=value)
            else:
                return ToolResult(success=True, result=dict(os.environ))
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))
