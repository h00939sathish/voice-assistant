
import time
import psutil
import logging
from datetime import datetime
from typing import Optional
from config import PROACTIVE_SETTINGS

logger = logging.getLogger(__name__)

class ProactiveEngine:
    """
    Engine for generating proactive suggestions based on system state and time.
    Run check_triggers() periodically from the main loop.
    """

    def __init__(self):
        self.settings = PROACTIVE_SETTINGS
        self.last_check = time.time()
        self.triggered_events = {
            "battery_low": 0,    # Timestamp of last trigger
            "morning_greeting": 0,
            "night_mode": 0,
            "idle_reminder": 0
        }
        # Cooldowns (seconds) to prevent nagging
        self.COOLDOWNS = {
            "battery_low": 1800,      # 30 mins
            "morning_greeting": 86400,# 24 hours
            "night_mode": 43200,      # 12 hours
            "idle_reminder": 7200     # 2 hours
        }
        logger.info("   🧠 Proactive Engine initialized")

    def check_triggers(self, last_activity_time: float) -> Optional[str]:
        """
        Check all triggers and return a suggestion string if active.
        Args:
            last_activity_time: Timestamp of last user interaction
        """
        if not self.settings.get("ENABLED", False):
            return None
        
        # Low-Power Mode: Disable proactive if battery < 15%
        battery = psutil.sensors_battery() if hasattr(psutil, "sensors_battery") else None
        if battery and not battery.power_plugged and battery.percent < 15:
            return None  # Save resources

        now = time.time()
        # Rate limit checks to avoid CPU usage
        if now - self.last_check < self.settings.get("CHECK_INTERVAL", 60):
            return None
        
        self.last_check = now

        # Priority 1: Battery (Critical)
        suggestion = self._check_battery()
        if suggestion:
            return suggestion

        # Priority 2: Time (Greeting/Night)
        suggestion = self._check_time_of_day()
        if suggestion:
            return suggestion

        # Priority 3: Idle (Engagement)
        suggestion = self._check_idle(last_activity_time)
        if suggestion:
            return suggestion

        return None

    def _check_battery(self) -> Optional[str]:
        """Check battery level against threshold"""
        if not hasattr(psutil, "sensors_battery"):
            return None
            
        battery = psutil.sensors_battery()
        if not battery or battery.power_plugged:
            return None

        threshold = self.settings.get("BATTERY_THRESHOLD", 20)
        
        if battery.percent <= threshold:
            if self._can_trigger("battery_low"):
                self._mark_triggered("battery_low")
                return f"Excuse me, your battery is at {battery.percent}%. Shall I enable power saver mode?"
        
        return None

    def _check_time_of_day(self) -> Optional[str]:
        """Check for morning/night triggers"""
        current_hour = datetime.now().hour
        
        # Morning Greeting
        morning_start = self.settings.get("MORNING_HOUR", 8)
        if current_hour == morning_start:
             if self._can_trigger("morning_greeting"):
                self._mark_triggered("morning_greeting")
                return "Good morning! I'm online. Should I read your daily briefing?"

        # Night Mode Suggestion
        night_start = self.settings.get("NIGHT_HOUR", 22)
        if current_hour >= night_start:
             if self._can_trigger("night_mode"):
                self._mark_triggered("night_mode")
                return "It's getting late. Would you like me to lower the screen brightness?"
                
        return None

    def _check_idle(self, last_activity: float) -> Optional[str]:
        """Check if user has been idle"""
        idle_duration = time.time() - last_activity
        threshold = self.settings.get("IDLE_THRESHOLD", 3600)
        
        if idle_duration > threshold:
             if self._can_trigger("idle_reminder"):
                self._mark_triggered("idle_reminder")
                return "I've noticed you've been quiet. Is there anything I can help you with?"
                
        return None

    def _can_trigger(self, event_name: str) -> bool:
        """Check if event is off cooldown"""
        last_time = self.triggered_events.get(event_name, 0)
        cooldown = self.COOLDOWNS.get(event_name, 3600)
        return (time.time() - last_time) > cooldown

    def _mark_triggered(self, event_name: str):
        """Update last trigger timestamp"""
        self.triggered_events[event_name] = time.time()
