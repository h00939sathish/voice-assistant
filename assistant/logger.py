"""
Logging configuration for Buddy Voice Assistant
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / f"buddy_{datetime.now().strftime('%Y%m%d')}.log"


class SafeConsoleHandler(logging.StreamHandler):
    """Stream handler that degrades gracefully on non-UTF Windows consoles."""

    def emit(self, record: logging.LogRecord) -> None:
        try:
            msg = self.format(record)
            stream = self.stream
            try:
                stream.write(msg + self.terminator)
            except UnicodeEncodeError:
                encoding = getattr(stream, "encoding", None) or "utf-8"
                safe_msg = (
                    (msg + self.terminator)
                    .encode(encoding, errors="replace")
                    .decode(encoding, errors="replace")
                )
                stream.write(safe_msg)
            self.flush()
        except Exception:
            self.handleError(record)


def setup_logger(name: str = "buddy") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        return logger

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s", datefmt="%H:%M:%S"
    )

    file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)

    console_handler = SafeConsoleHandler(sys.stdout)
    console_handler.setLevel(logging.INFO)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    return logger


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"buddy.{name}")
