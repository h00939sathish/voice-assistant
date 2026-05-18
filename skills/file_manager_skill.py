import os
from pathlib import Path
from typing import Any

from skills.base_skill import BaseSkill, skill


@skill(
    name="file_manager",
    keywords=[
        "find file",
        "search for file",
        "list files",
        "show files",
        "what's in",
        "read file",
        "open file content",
        "latest download",
        "move file",
        "copy file",
        "delete file",
        "where is",
    ],
    description="Manage files: list, find, read, and organize",
)
class FileManagerSkill(BaseSkill):
    """
    Skill for managing files and directories on the local system.
    """

    def __init__(self):
        super().__init__()
        self.name = "file_manager"
        self.description = "Manage files: list, find, read, and organize"
        self.keywords = [
            "find file",
            "search for file",
            "list files",
            "show files",
            "what's in",
            "read file",
            "open file content",
            "latest download",
            "move file",
            "copy file",
            "delete file",
        ]

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        # Simple routing based on key phrases
        text_lower = text.lower()

        if (
            "list" in text_lower
            or "show files" in text_lower
            or "what's in" in text_lower
        ):
            return self._handle_list(text, context)

        if "find" in text_lower or "search" in text_lower or "where is" in text_lower:
            return self._handle_find(text, context)

        if "read" in text_lower or "content" in text_lower:
            return self._handle_read(text, context)

        if "latest download" in text_lower:
            return self._handle_latest_download(text, context)

        # Fallback: let the LLM handle complex logic if needed, or return generic help
        return "I can help you list, find, and read files. What woud you like to do?"

    def _handle_list(self, text: str, context: dict[str, Any]) -> str:
        # Try to extract path
        path_str = "."
        if "in" in text:
            parts = text.split("in")
            if len(parts) > 1:
                target = parts[1].strip()
                # Common shortcuts
                if "downloads" in target.lower():
                    path_str = str(Path.home() / "Downloads")
                elif "documents" in target.lower():
                    path_str = str(Path.home() / "Documents")
                elif "desktop" in target.lower():
                    path_str = str(Path.home() / "Desktop")
                elif "current" in target.lower() or "here" in target.lower():
                    path_str = "."
                else:
                    path_str = target.strip(".")  # strict cleaning?

        try:
            p = Path(path_str).resolve()
            if not p.exists():
                return f"I couldn't find the directory: {path_str}"

            items = list(p.glob("*"))
            if not items:
                return f"The directory '{p.name}' is empty."

            # Format output (limit 10)
            file_list = [
                f"- {item.name}" + ("/" if item.is_dir() else "") for item in items[:10]
            ]
            remaining = len(items) - 10

            response = f"Here are the files in {p.name}:\n" + "\n".join(file_list)
            if remaining > 0:
                response += f"\n...and {remaining} more."
            return response

        except Exception as e:
            return f"Error listing files: {e}"

    def _handle_find(self, text: str, context: dict[str, Any]) -> str:
        # Extract filename
        query = text.split("find")[-1].split("search")[-1].strip()
        if "my" in query:
            query = query.replace("my", "").strip()

        search_root = Path.home()
        # Limit search depth / locations for performance
        results = []

        try:
            # Quick search in Documents and Desktop first
            for root in [
                search_root / "Documents",
                search_root / "Desktop",
                search_root / "Downloads",
            ]:
                if root.exists():
                    found = list(root.rglob(f"*{query}*"))
                    results.extend(found[:5])  # limit 5 per root

            if not results:
                return (
                    f"I couldn't find any file matching '{query}' in your main folders."
                )

            response = "I found these files:\n" + "\n".join(
                [f"- {str(f)}" for f in set(results)]
            )
            return response

        except Exception as e:
            return f"Search error: {e}"

    def _handle_read(self, text: str, context: dict[str, Any]) -> str:
        # Extract filename (simple heuristic)
        words = text.split()
        target_file = words[-1]  # Assume last word is filename for now

        # Determine path (assume current or try to find)
        p = Path(target_file)
        if not p.exists():
            return f"I cannot find the file '{target_file}'."

        try:
            if p.stat().st_size > 10000:
                return "That file is too large for me to read aloud."

            content = p.read_text(errors="replace")
            summary = content[:500] + ("..." if len(content) > 500 else "")
            return f"Content of {target_file}:\n{summary}"
        except Exception as e:
            return f"Error reading file: {e}"

    def _handle_latest_download(self, text: str, context: dict[str, Any]) -> str:
        downloads = Path.home() / "Downloads"
        if not downloads.exists():
            return "Downloads folder not found."

        try:
            # Sort by mtime
            files = list(downloads.glob("*"))
            if not files:
                return "Downloads folder is empty."

            latest = max(files, key=os.path.getctime)
            return f"Your latest download is: {latest.name}"
        except Exception as e:
            return f"Error checking downloads: {e}"
