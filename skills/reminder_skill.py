"""
Reminder Skill - Sets alarms and reminders
"""
import sqlite3
import uuid
import logging
import re
from datetime import datetime, timedelta
from typing import Dict, Any
from pathlib import Path

# Add project root to path
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from assistant.scheduler import Scheduler

logger = logging.getLogger(__name__)

SKILL_META = {
    "name": "Reminder",
    "description": "Sets alarms, one-time reminders, and recurring cron jobs",
    "keywords": ["remind", "alarm", "timer", "schedule", "alert"],
    "version": "2.0.0"
}

class ReminderSkill:
    """
    Sets reminders/alarms and triggers them via the central Scheduler.
    Supports simple timers and recurring cron jobs.
    """
    
    def __init__(self):
        self.keywords = ["remind", "alarm", "timer", "alert", "schedule"]
        self.db_path = Path(__file__).parent.parent / "cache" / "reminders.db"
        self._tts_callback = None
        
        # Initialize Scheduler
        self.scheduler = Scheduler()
        self.scheduler.start()
        
        # Ensure DB exists
        if not self.db_path.parent.exists():
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            
        self._init_db()
        self._restore_jobs()

    def set_tts_callback(self, tts):
        """Set TTS callback for announcing reminders"""
        self._tts_callback = tts

    def _get_connection(self):
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    def _init_db(self):
        """Initialize database with support for recurring jobs"""
        try:
            with self._get_connection() as conn:
                # Create table if not exists
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id TEXT PRIMARY KEY,
                        message TEXT NOT NULL,
                        trigger_time DATETIME,
                        cron_expr TEXT,
                        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                        status TEXT DEFAULT 'pending'
                    )
                """)
                
                # Check if cron_expr column exists (migration)
                cursor = conn.execute("PRAGMA table_info(reminders)")
                columns = [info[1] for info in cursor.fetchall()]
                if "cron_expr" not in columns:
                    logger.info("Migrating DB: Adding cron_expr column")
                    conn.execute("ALTER TABLE reminders ADD COLUMN cron_expr TEXT")
                    
        except Exception as e:
            logger.error(f"Failed to init reminder DB: {e}")

    def _restore_jobs(self):
        """Restore pending jobs from DB to Scheduler on startup"""
        try:
            with self._get_connection() as conn:
                cursor = conn.execute("""
                    SELECT id, message, trigger_time, cron_expr 
                    FROM reminders 
                    WHERE status = 'pending'
                """)
                count = 0
                for row in cursor.fetchall():
                    rid, msg, trigger_str, cron = row
                    
                    # Callback wrapper
                    callback = lambda m=msg, r=rid: self._trigger_alert(m, r)
                    
                    if cron:
                        # Restore recurring
                        self.scheduler.schedule_cron(rid, cron, callback)
                        count += 1
                    elif trigger_str:
                        # Restore one-time if in future
                        trigger_dt = datetime.fromisoformat(trigger_str) if isinstance(trigger_str, str) else trigger_str
                        if trigger_dt > datetime.now():
                            self.scheduler.schedule_once(rid, trigger_dt, callback)
                            count += 1
                        else:
                            # Mark missed jobs as completed (or handle missed)
                            pass 
                            
            logger.info(f"   ⏰ Restored {count} reminders")
            
        except Exception as e:
            logger.error(f"Failed to restore jobs: {e}")

    def _trigger_alert(self, message: str, reminder_id: str):
        """Trigger the actual alert"""
        print(f"\n⏰ ALERT: {message}\n")
        
        # Mark as completed only if NOT recurring (cron jobs run forever until cancelled)
        # Actually, if we use schedule_once, we should mark as completed.
        # If cron, we leave it as pending logic is handled by scheduler rescheduling?
        # The scheduler handles rescheduling in memory.
        # But for persistence, we keep 'pending' status for recurring.
        # For one-time, we should mark as done.
        
        is_recurring = False
        with self._get_connection() as conn:
            cursor = conn.execute("SELECT cron_expr FROM reminders WHERE id=?", (reminder_id,))
            row = cursor.fetchone()
            if row and row[0]:
                is_recurring = True
            
            if not is_recurring:
                conn.execute("UPDATE reminders SET status = 'completed' WHERE id = ?", (reminder_id,))
        
        # Speak
        if self._tts_callback:
            try:
                self._tts_callback.speak(f"Reminder: {message}")
            except Exception as e:
                print(f"Failed to speak reminder: {e}")

    async def handle(self, text: str, context: Dict[str, Any]) -> str:
        """Handle reminder requests with cron support"""
        text = text.lower()
        
        # Check for simple cancellation
        if "cancel" in text or "delete" in text:
            # Simplistic cancellation
            return "To cancel a reminder, please manage it via the dashboard/database (Cancellation not fully implemented via voice yet)."
            
        # Parse recurrence "every X"
        # "Remind me every day at 9 am to ..."
        cron_expr = None
        recurring_match = False
        
        if "every day" in text or "daily" in text:
            cron_expr = "0 9 * * *" # Default 9 AM if time not specified
            recurring_match = True
            
        # Handle simple one-time reminders logic (reused from old skill)
        duration = 0
        message = "Time's up!"
        
        # Extract time for one-time
        if not recurring_match:
            m_min = re.search(r"(\d+)\s*(?:min|minute)", text)
            if m_min: duration += int(m_min.group(1)) * 60
            
            m_sec = re.search(r"(\d+)\s*(?:sec|second)", text)
            if m_sec: duration += int(m_sec.group(1))
            
            m_hour = re.search(r"(\d+)\s*(?:hour|hr)", text)
            if m_hour: duration += int(m_hour.group(1)) * 3600

        # Extract message
        m_msg = re.search(r"(?:to|that)\s+(.+)$", text)
        if m_msg:
            message = m_msg.group(1).strip()
        
        # DB Persistence
        cid = str(uuid.uuid4())
        
        if recurring_match:
            # Basic Hack for "every day at X"
            # Extract time "at 5 pm"
            m_time = re.search(r"at\s+(\d+)(?::(\d+))?\s*(am|pm)?", text)
            if m_time:
                h = int(m_time.group(1))
                m = int(m_time.group(2) or 0)
                ampm = m_time.group(3)
                if ampm == "pm" and h < 12: h += 12
                if ampm == "am" and h == 12: h = 0
                cron_expr = f"{m} {h} * * *"
            
            # Save
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO reminders (id, message, cron_expr) VALUES (?, ?, ?)",
                    (cid, message, cron_expr)
                )
            
            # Schedule
            self.scheduler.schedule_cron(cid, cron_expr, lambda: self._trigger_alert(message, cid))
            return f"Set recurring reminder: '{message}' with schedule {cron_expr}"
            
        elif duration > 0:
            trigger_time = datetime.now() + timedelta(seconds=duration)
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO reminders (id, message, trigger_time) VALUES (?, ?, ?)",
                    (cid, message, trigger_time)
                )
            
            self.scheduler.schedule_once(cid, trigger_time, lambda: self._trigger_alert(message, cid))
            time_str = trigger_time.strftime("%I:%M %p")
            return f"OK, set reminder for {message} at {time_str}."
            
        return "I didn't understand the time. Try 'Remind me in 5 minutes' or 'Remind me every day at 9am'."

    def stop(self):
        self.scheduler.stop()
