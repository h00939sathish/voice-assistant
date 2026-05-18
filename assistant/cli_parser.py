import argparse
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Buddy Voice Assistant",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--config",
        type=Path,
        help="Path to custom config file",
    )
    parser.add_argument(
        "--dashboard-host",
        type=str,
        default="127.0.0.1",
        help="Dashboard host (default: 127.0.0.1)",
    )
    parser.add_argument(
        "--dashboard-port",
        type=int,
        default=5050,
        help="Dashboard port (default: 5050)",
    )
    return parser.parse_args()
