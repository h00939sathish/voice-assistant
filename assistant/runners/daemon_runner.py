"""
Daemon Runner - Launches Buddy in headless server mode (for Docker / Cloud / Remote access).
"""

import logging
import os
import sys

logger = logging.getLogger("daemon_runner")


def run_daemon(host: str = "0.0.0.0", port: int = 8000) -> None:
    """Start Buddy API server in headless daemon mode."""
    logger.info(f"🚀 Starting Buddy Daemon on {host}:{port}")

    try:
        import uvicorn

        from assistant.api_server import app as api_app

        uvicorn.run(
            api_app,
            host=host,
            port=port,
            log_level="info",
        )
    except KeyboardInterrupt:
        logger.info("Daemon shutting down gracefully...")
    except Exception as e:
        logger.critical(f"Daemon crashed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    port = int(os.environ.get("PORT", "8000"))
    run_daemon(port=port)
