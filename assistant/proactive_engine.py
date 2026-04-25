
import time
import psutil
import logging
from datetime import datetime
from typing import Optional
from config import (
    PROACTIVE_SETTINGS,
    DESKTOP_AWARENESS_ENABLED,
    DESKTOP_AWARENESS_INTERVAL,
    DESKTOP_AWARENESS_OCR,
    DESKTOP_AWARENESS_HISTORY,
)

logger = logging.getLogger(__name__)

class ProactiveEngine:
    """
    Engine for generating proactive suggestions based on system state, time,
    and desktop awareness (screen context).
    Run check_triggers() periodically from the main loop.
    """

    def __init__(self):
        self.settings = PROACTIVE_SETTINGS
        self.last_check = time.time()
        self.triggered_events = {
            "battery_low": 0,
            "low_memory": 0,
            "morning_greeting": 0,
            "night_mode": 0,
            "idle_reminder": 0,
            # "screen_issue": 0,  # Disabled - unstable
        }
        self.COOLDOWNS = {
            "battery_low": 1800,
            "low_memory": 1800,
            "morning_greeting": 86400,
            "night_mode": 43200,
            "idle_reminder": 7200,
            # "screen_issue": 300,  # Disabled
        }

        # Desktop Awareness
        self.desktop_awareness = None
        if DESKTOP_AWARENESS_ENABLED:
            try:
                from assistant.desktop_awareness import DesktopAwareness
                self.desktop_awareness = DesktopAwareness(
                    interval=DESKTOP_AWARENESS_INTERVAL,
                    ocr_enabled=DESKTOP_AWARENESS_OCR,
                    history_size=DESKTOP_AWARENESS_HISTORY,
                )
                self.desktop_awareness.start()
            except Exception as e:
                logger.warning(f"   ⚠️ Desktop Awareness init failed: {e}")

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
            return None

        now = time.time()
        if now - self.last_check < self.settings.get("CHECK_INTERVAL", 60):
            return None
        
        self.last_check = now

        # Priority 1: Battery (Critical)
        suggestion = self._check_battery()
        if suggestion:
            return suggestion

        # Priority 2: System Memory
        suggestion = self._check_low_memory()
        if suggestion:
            return suggestion

        # Priority 3: Time (Greeting/Night)
        suggestion = self._check_time_of_day()
        if suggestion:
            return suggestion

        # Priority 4: Screen Awareness (Error/Struggle detection) - disable if unstable
        # suggestion = self._check_screen_context()
        # if suggestion:
        #     return suggestion

        # Priority 5: Idle (Engagement)
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
                return "Good morning! I've prepared your daily briefing. Would you like to hear it?"
        
        # Night Mode Suggestion  
        night_start = self.settings.get("NIGHT_HOUR", 22)
        if current_hour >= night_start:
             if self._can_trigger("night_mode"):
                self._mark_triggered("night_mode")
                return "It's getting late. Should I enable night mode and reduce screen brightness?"
                
        return None

    def _check_memory_context(self, memory_system) -> Optional[str]:
        """Check memory for relevant context or remind about important items"""
        if not memory_system or not self.settings.get("CONTEXT_AWARENESS", True):
            return None
        
        try:
            # Get pending items or important memories
            stats = memory_system.get_stats()
            if stats and stats.get("total_memories", 0) > 0:
                # Could offer to recall something relevant
                pass
        except Exception:
            pass
        return None

    def _check_low_memory(self) -> Optional[str]:
        """Check system memory (RAM) levels"""
        if not self.settings.get("LOW_MEMORY_WARNING_MB"):
            return None
        
        try:
            mem = psutil.virtual_memory()
            available_mb = mem.available / (1024 * 1024)
            threshold = self.settings.get("LOW_MEMORY_WARNING_MB", 512)
            
            if available_mb < threshold:
                if self._can_trigger("low_memory"):
                    self._mark_triggered("low_memory")
                    return f"Your computer is running low on memory ({available_mb:.0f}MB available). Should I close some applications?"
        except Exception:
            pass
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

    def _check_screen_context(self) -> Optional[str]:
        """Check desktop screen for errors or user struggles via OCR."""
        if not self.desktop_awareness:
            return None

        try:
            issue = self.desktop_awareness.detect_issues()
            if issue and self._can_trigger("screen_issue"):
                self._mark_triggered("screen_issue")
                return issue
        except Exception:
            pass

        return None


    def _can_trigger(self, event_name: str) -> bool:
        """Check if event is off cooldown"""
        last_time = self.triggered_events.get(event_name, 0)
        cooldown = self.COOLDOWNS.get(event_name, 3600)
        return (time.time() - last_time) > cooldown

    def _mark_triggered(self, event_name: str):
        """Update last trigger timestamp"""
        self.triggered_events[event_name] = time.time()
