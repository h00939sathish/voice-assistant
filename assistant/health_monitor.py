"""
Health Monitor - Watchdog for system stability and auto-recovery
"""

import logging
import threading
import time
from datetime import datetime

logger = logging.getLogger(__name__)


class HealthMonitor:
    """
    Monitors system health and handles automatic recovery from crashes.
    """

    def __init__(self, check_interval: int = 5, timeout: int = 30):
        self.check_interval = check_interval
        self.timeout = timeout
        self.last_heartbeat = time.time()
        self.running = False
        self._monitor_thread = None
        self._crash_count = 0

    def start(self):
        """Start the monitoring thread"""
        self.running = True
        self.last_heartbeat = time.time()
        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()
        logger.info("   🩺 Health monitor started")

    def heartbeat(self):
        """Signal that the main loop is alive"""
        self.last_heartbeat = time.time()

    def _monitor_loop(self):
        """Watchdog loop"""
        while self.running:
            time.sleep(self.check_interval)

            elapsed = time.time() - self.last_heartbeat
            if elapsed > self.timeout:
                logger.warning(f"   ⚠️ System frozen? No heartbeat for {elapsed:.1f}s")
                # In a more complex system, we might trigger a restart here
                # For now, we just log it aggressively

    def stop(self):
        self.running = False

    def log_crash(self, error: Exception):
        """Log a critical error with timestamp"""
        self._crash_count += 1
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        msg = f"💥 CRASH #{self._crash_count} at {timestamp}: {error}"
        print(f"\n{msg}\n")
        logger.critical(msg, exc_info=True)

        # Simple backoff logic
        if self._crash_count > 5:
            print("   ⚠️ Too many crashes, waiting before restart...")
            time.sleep(5)


# Singleton
_monitor = HealthMonitor()


def get_monitor():
    return _monitor
