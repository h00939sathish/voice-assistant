from pathlib import Path

from .base import BaseTool, ToolResult


class FileReadTool(BaseTool):
    name = "file_read"
    description = "Read contents of a file"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to the file"}
        },
        "required": ["path"],
    }

    async def execute(self, path: str, **kwargs) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return ToolResult(
                    success=False, result=None, error=f"File not found: {path}"
                )

            content = file_path.read_text(encoding="utf-8")
            return ToolResult(
                success=True, result=content, metadata={"path": str(file_path)}
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class FileWriteTool(BaseTool):
    name = "file_write"
    description = "Write content to a file. WARNING: overwrites existing files!"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Full path to the file"},
            "content": {"type": "string", "description": "Content to write"},
        },
        "required": ["path", "content"],
    }

    async def execute(self, path: str, content: str, **kwargs) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            return ToolResult(
                success=True,
                result=f"Written to {file_path}",
                metadata={"path": str(file_path)},
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class FileListTool(BaseTool):
    name = "file_list"
    description = "List files in a directory"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path"},
            "pattern": {"type": "string", "description": "Optional glob pattern"},
            "recursive": {
                "type": "boolean",
                "description": "List recursively",
                "default": False,
            },
        },
        "required": ["path"],
    }

    async def execute(
        self, path: str, pattern: str = "*", recursive: bool = False, **kwargs
    ) -> ToolResult:
        try:
            dir_path = Path(path).expanduser().resolve()
            if not dir_path.exists():
                return ToolResult(
                    success=False, result=None, error=f"Directory not found: {path}"
                )

            if recursive:
                files = list(dir_path.rglob(pattern))
            else:
                files = list(dir_path.glob(pattern))

            results = []
            for f in files:
                results.append(
                    {
                        "name": f.name,
                        "path": str(f),
                        "type": "dir" if f.is_dir() else "file",
                        "size": f.stat().st_size if f.is_file() else None,
                    }
                )

            return ToolResult(
                success=True, result=results, metadata={"count": len(results)}
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class FileSearchTool(BaseTool):
    name = "file_search"
    description = "Search for files by name pattern"
    parameters = {
        "type": "object",
        "properties": {
            "root": {"type": "string", "description": "Root directory to search"},
            "pattern": {"type": "string", "description": "Glob pattern (e.g., *.py)"},
            "max_results": {
                "type": "integer",
                "description": "Maximum results",
                "default": 50,
            },
        },
        "required": ["root", "pattern"],
    }

    async def execute(
        self, root: str, pattern: str = "*", max_results: int = 50, **kwargs
    ) -> ToolResult:
        try:
            root_path = Path(root).expanduser().resolve()
            if not root_path.exists():
                return ToolResult(
                    success=False, result=None, error=f"Directory not found: {root}"
                )

            files = list(root_path.rglob(pattern))[:max_results]
            results = [{"name": f.name, "path": str(f)} for f in files]

            return ToolResult(
                success=True, result=results, metadata={"count": len(results)}
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class FileGrepTool(BaseTool):
    name = "file_grep"
    description = "Search for text within files"
    parameters = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string", "description": "Text pattern to search"},
            "path": {"type": "string", "description": "Directory to search"},
            "file_pattern": {
                "type": "string",
                "description": "File glob pattern",
                "default": "*",
            },
            "max_results": {
                "type": "integer",
                "description": "Max files to search",
                "default": 20,
            },
        },
        "required": ["pattern", "path"],
    }

    async def execute(
        self,
        pattern: str,
        path: str,
        file_pattern: str = "*",
        max_results: int = 20,
        **kwargs,
    ) -> ToolResult:
        try:
            root_path = Path(path).expanduser().resolve()
            results = []

            for file_path in root_path.rglob(file_pattern):
                if file_path.is_file() and len(results) < max_results:
                    try:
                        content = file_path.read_text(encoding="utf-8", errors="ignore")
                        if pattern in content:
                            lines = content.split("\n")
                            matches = [
                                i + 1 for i, line in enumerate(lines) if pattern in line
                            ]
                            results.append(
                                {
                                    "file": str(file_path),
                                    "matches": matches[:5],
                                    "context": "Found",
                                }
                            )
                    except Exception:
                        continue

            return ToolResult(
                success=True, result=results, metadata={"files_found": len(results)}
            )
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class FileTreeTool(BaseTool):
    name = "file_tree"
    description = "Show directory tree structure"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Directory path"},
            "depth": {"type": "integer", "description": "Max depth", "default": 3},
        },
        "required": ["path"],
    }

    async def execute(self, path: str, depth: int = 3, **kwargs) -> ToolResult:
        try:
            root = Path(path).expanduser().resolve()

            def build_tree(p: Path, current_depth: int = 0) -> str:
                if current_depth >= depth:
                    return ""

                result = []
                try:
                    items = sorted(p.iterdir(), key=lambda x: (not x.is_dir(), x.name))
                    for item in items[:20]:
                        prefix = "📁 " if item.is_dir() else "📄 "
                        result.append(f"{'  ' * current_depth}{prefix}{item.name}")
                        if item.is_dir():
                            result.append(build_tree(item, current_depth + 1))
                except PermissionError:
                    pass
                return "\n".join(result)

            tree = build_tree(root)
            return ToolResult(success=True, result=tree, metadata={"path": str(root)})
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))


class FileStatTool(BaseTool):
    name = "file_stat"
    description = "Get file/directory statistics"
    parameters = {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "File or directory path"}
        },
        "required": ["path"],
    }

    async def execute(self, path: str, **kwargs) -> ToolResult:
        try:
            file_path = Path(path).expanduser().resolve()
            if not file_path.exists():
                return ToolResult(
                    success=False, result=None, error=f"Path not found: {path}"
                )

            stat = file_path.stat()
            result = {
                "path": str(file_path),
                "name": file_path.name,
                "type": "directory" if file_path.is_dir() else "file",
                "size": stat.st_size,
                "created": stat.st_ctime,
                "modified": stat.st_mtime,
                "accessed": stat.st_atime,
            }
            return ToolResult(success=True, result=result)
        except Exception as e:
            return ToolResult(success=False, result=None, error=str(e))
