"""
Reminder Skill — Full lifecycle: create, list, cancel, recurring.
Reminders are stored in cache/reminders.db and triggered via the Scheduler.
"""

import asyncio
import logging
import os
import re
import sqlite3
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from skills.base_skill import BaseSkill, skill

logger = logging.getLogger(__name__)

_DB_PATH = Path(__file__).parent.parent / "cache" / "reminders.db"


@skill(
    name="reminder",
    keywords=[
        "remind",
        "reminder",
        "alarm",
        "timer",
        "schedule",
        "alert",
        "set a timer",
        "set an alarm",
        "list reminders",
        "show reminders",
        "cancel reminder",
        "delete reminder",
        "cancel all reminders",
        "google calendar",
        "add to calendar",
    ],
    description="Creates, lists, and cancels reminders and timers with SQLite persistence",
    priority=7,
)
class ReminderSkill(BaseSkill):
    """Full reminder lifecycle: create / list / cancel / recurring."""

    def __init__(self):
        super().__init__()
        self.db_path = _DB_PATH
        self._tts = None
        self._scheduler = None
        self._scheduler_loaded = False
        self._calendar_skill = None
        self._auto_calendar_sync = os.getenv(
            "REMINDER_AUTO_SYNC_CALENDAR", "false"
        ).lower() in {"1", "true", "yes"}
        raw_duration = os.getenv("REMINDER_CALENDAR_DEFAULT_MINUTES", "30")
        try:
            self._calendar_default_duration = max(1, int(raw_duration))
        except ValueError:
            self._calendar_default_duration = 30
            logger.warning(
                f"Invalid REMINDER_CALENDAR_DEFAULT_MINUTES ('{raw_duration}'). Defaulting to 30."
            )

        if self._auto_calendar_sync:
            try:
                pass
            except Exception as e:
                logger.warning(
                    f"REMINDER_AUTO_SYNC_CALENDAR is enabled, but Calendar integration is unavailable: {e}"
                )

        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    # ------------------------------------------------------------------
    # Setup
    # ------------------------------------------------------------------

    def set_tts_callback(self, tts):
        self._tts = tts

    def _get_connection(self):
        return sqlite3.connect(str(self.db_path), check_same_thread=False)

    def _init_db(self):
        try:
            with self._get_connection() as conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS reminders (
                        id          TEXT PRIMARY KEY,
                        message     TEXT NOT NULL,
                        trigger_time DATETIME,
                        cron_expr   TEXT,
                        created_at  DATETIME DEFAULT CURRENT_TIMESTAMP,
                        status      TEXT DEFAULT 'pending'
                    )
                """)
        except Exception as e:
            logger.error(f"Failed to init reminder DB: {e}")

    def _get_scheduler(self):
        if not self._scheduler_loaded:
            try:
                from assistant.scheduler import Scheduler

                self._scheduler = Scheduler()
                self._scheduler.start()
                self._scheduler_loaded = True
                self._restore_jobs()
                logger.info("   ⏰ Scheduler started")
            except Exception as e:
                logger.error(f"Scheduler init failed: {e}")
        return self._scheduler

    def _wants_calendar_sync(self, text: str) -> bool:
        """Enable Google Calendar sync on explicit user phrasing or env toggle."""
        if self._auto_calendar_sync:
            return True
        markers = (
            "google calendar",
            "on calendar",
            "to calendar",
            "add to calendar",
            "calendar event",
            "schedule on calendar",
        )
        return any(m in text for m in markers)

    def _get_calendar_skill(self):
        """Lazy-load calendar skill without forcing auth prompts."""
        if self._calendar_skill is not None:
            return self._calendar_skill
        try:
            from skills.calendar_skill import CalendarSkill

            self._calendar_skill = CalendarSkill()
            return self._calendar_skill
        except Exception as e:
            logger.warning(f"Calendar integration unavailable: {e}")
            return None

    def _calendar_create_event_sync(
        self,
        summary: str,
        start_dt: datetime,
        duration_minutes: int,
        recurring_daily: bool = False,
    ) -> tuple[bool, str]:
        """
        Create a Google Calendar event if auth is already configured.
        Returns: (success, message)
        """
        cal = self._get_calendar_skill()
        if not cal:
            return False, "calendar integration unavailable"

        try:
            if not getattr(cal, "_auth_completed", False):
                cal._authenticate(interactive=False)
        except Exception:
            pass

        if not getattr(cal, "_auth_completed", False) or not getattr(
            cal, "service", None
        ):
            return False, "Google Calendar is not connected yet"

        # Ensure a timezone-aware datetime for Calendar API
        local_tz = datetime.now().astimezone().tzinfo
        if start_dt.tzinfo is None and local_tz is not None:
            start_dt = start_dt.replace(tzinfo=local_tz)
        end_dt = start_dt + timedelta(minutes=max(1, duration_minutes))

        if not recurring_daily:
            try:
                conflicts = cal._check_conflicts(start_dt, end_dt)
                if conflicts:
                    return False, f"calendar conflict with '{conflicts[0]}'"
            except Exception:
                pass

        event = {
            "summary": summary,
            "start": {"dateTime": start_dt.isoformat()},
            "end": {"dateTime": end_dt.isoformat()},
        }
        if recurring_daily:
            event["recurrence"] = ["RRULE:FREQ=DAILY"]

        try:
            cal.service.events().insert(calendarId="primary", body=event).execute()
            if recurring_daily:
                return True, "added recurring event to Google Calendar"
            return True, "added event to Google Calendar"
        except Exception as e:
            logger.error(f"Calendar sync failed: {e}")
            return False, "calendar API error"

    @staticmethod
    def _strip_calendar_markers(message: str) -> str:
        cleaned = re.sub(
            r"\s+(?:on|to)\s+(?:google\s+)?calendar\b.*$",
            "",
            message,
            flags=re.IGNORECASE,
        ).strip()
        return cleaned or message

    def _restore_jobs(self):
        """Re-schedule pending reminders after restart."""
        try:
            sched = self._scheduler
            if not sched:
                return
            with self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT id, message, trigger_time, cron_expr "
                    "FROM reminders WHERE status = 'pending'"
                )
                count = 0
                for rid, msg, trigger_str, cron in cursor.fetchall():

                    def make_cb(message: str, reminder_id: str):
                        def cb():
                            self._trigger_alert(message, reminder_id)

                        return cb

                    cb = make_cb(msg, rid)
                    if cron:
                        sched.schedule_cron(rid, cron, cb)
                        count += 1
                    elif trigger_str:
                        try:
                            dt = datetime.fromisoformat(trigger_str)
                            if dt > datetime.now():
                                sched.schedule_once(rid, dt, cb)
                                count += 1
                        except ValueError:
                            pass
            logger.info(f"   ⏰ Restored {count} pending reminders")
        except Exception as e:
            logger.error(f"Failed to restore jobs: {e}")

    def _trigger_alert(self, message: str, reminder_id: str):
        """Called when a reminder fires."""
        # Re-check status at fire time so cancelled reminders never announce.
        final_message = message
        is_recurring = False
        with self._get_connection() as conn:
            row = conn.execute(
                "SELECT message, status, cron_expr FROM reminders WHERE id=?",
                (reminder_id,),
            ).fetchone()
            if not row:
                return
            stored_message, status, cron_expr = row
            if status != "pending":
                logger.info(
                    f"Skipping inactive reminder '{reminder_id}' (status={status})"
                )
                return

            final_message = stored_message or message
            is_recurring = bool(cron_expr)
            if not is_recurring:
                conn.execute(
                    "UPDATE reminders SET status = 'completed' WHERE id = ?",
                    (reminder_id,),
                )

        logger.info(f"   ⏰ ALERT: {final_message}")
        print(f"\n⏰ REMINDER: {final_message}\n")

        if self._tts:
            try:
                if hasattr(self._tts, "speak"):
                    self._tts.speak(f"Reminder: {final_message}")
                else:
                    loop = asyncio.new_event_loop()
                    loop.run_until_complete(
                        self._tts.speak_streaming(f"Reminder: {final_message}")
                    )
                    loop.close()
            except Exception as e:
                logger.error(f"TTS for reminder failed: {e}")

    # ------------------------------------------------------------------
    # Intent handler
    # ------------------------------------------------------------------

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        lower = text.lower()

        # Ensure scheduler is ready
        self._get_scheduler()

        # --- LIST ---
        if any(w in lower for w in ("list", "show", "what reminders", "my reminders")):
            return self._list_reminders()

        # --- CANCEL ALL ---
        if "cancel all" in lower or "delete all" in lower:
            return self._cancel_all()

        # --- CANCEL ONE (by number or keyword) ---
        if any(w in lower for w in ("cancel", "delete", "remove")):
            return self._cancel_one(lower)

        # --- CREATE ---
        return await self._create_reminder(text, lower)

    # ------------------------------------------------------------------
    # CRUD helpers
    # ------------------------------------------------------------------

    def _list_reminders(self) -> str:
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT message, trigger_time, cron_expr FROM reminders "
                    "WHERE status = 'pending' ORDER BY trigger_time ASC"
                ).fetchall()
            if not rows:
                return "You have no pending reminders."
            parts = []
            for i, (msg, trigger_str, cron) in enumerate(rows, 1):
                if cron:
                    parts.append(f"{i}. '{msg}' — recurring ({cron})")
                elif trigger_str:
                    try:
                        dt = datetime.fromisoformat(trigger_str)
                        parts.append(
                            f"{i}. '{msg}' — at {dt.strftime('%I:%M %p on %b %d')}"
                        )
                    except ValueError:
                        parts.append(f"{i}. '{msg}'")
            return "Your reminders: " + ". ".join(parts) + "."
        except Exception as e:
            logger.error(f"List reminders failed: {e}")
            return "I couldn't list your reminders right now."

    def _cancel_all(self) -> str:
        try:
            reminder_ids = []
            with self._get_connection() as conn:
                reminder_ids = [
                    row[0]
                    for row in conn.execute(
                        "SELECT id FROM reminders WHERE status = 'pending'"
                    ).fetchall()
                ]
                cur = conn.execute(
                    "UPDATE reminders SET status = 'cancelled' WHERE status = 'pending'"
                )
                count = cur.rowcount

            # Unschedule only affected jobs
            if self._scheduler:
                for rid in reminder_ids:
                    self._scheduler.cancel(name=rid)

            return f"Cancelled {count} reminder{'s' if count != 1 else ''}."
        except Exception as e:
            logger.error(f"Cancel all failed: {e}")
            return "I couldn't cancel your reminders."

    def _cancel_one(self, text: str) -> str:
        """Cancel by index ('cancel reminder 2') or keyword match."""
        try:
            with self._get_connection() as conn:
                rows = conn.execute(
                    "SELECT id, message FROM reminders WHERE status = 'pending' "
                    "ORDER BY trigger_time ASC"
                ).fetchall()

            if not rows:
                return "You have no pending reminders to cancel."

            # Try numeric index first
            m = re.search(r"\b(\d+)\b", text)
            if m:
                idx = int(m.group(1)) - 1
                if 0 <= idx < len(rows):
                    rid, msg = rows[idx]
                    return self._delete_by_id(rid, msg)
                return f"I don't have a reminder number {m.group(1)}."

            # Try fuzzy keyword match — cancel the first one whose message matches
            from difflib import get_close_matches

            messages = [r[1].lower() for r in rows]
            words = [
                w
                for w in text.split()
                if w not in ("cancel", "delete", "remove", "reminder")
            ]
            query = " ".join(words).strip()
            if query:
                matches = get_close_matches(query, messages, n=1, cutoff=0.4)
                if matches:
                    idx = messages.index(matches[0])
                    rid, msg = rows[idx]
                    return self._delete_by_id(rid, msg)

            return (
                "Which reminder? Say 'cancel reminder 1' or 'cancel all reminders'. "
                + self._list_reminders()
            )
        except Exception as e:
            logger.error(f"Cancel one failed: {e}")
            return "I couldn't cancel that reminder."

    def _delete_by_id(self, rid: str, msg: str) -> str:
        with self._get_connection() as conn:
            conn.execute(
                "UPDATE reminders SET status = 'cancelled' WHERE id = ?", (rid,)
            )
        if self._scheduler:
            try:
                self._scheduler.cancel(name=rid)
            except Exception:
                pass
        return f"Cancelled reminder: '{msg}'."

    async def _create_reminder(self, original_text: str, text: str) -> str:
        """Parse time expression and create a new reminder."""
        wants_calendar_sync = self._wants_calendar_sync(text)

        # --- Recurring ---
        cron_expr: str | None = None
        if "every day" in text or "daily" in text:
            cron_expr = "0 9 * * *"  # default 9am
            m_time = re.search(r"at\s+(\d+)(?::(\d+))?\s*(am|pm)?", text)
            if m_time:
                h = int(m_time.group(1))
                mins = int(m_time.group(2) or 0)
                ampm = m_time.group(3)
                if ampm == "pm" and h < 12:
                    h += 12
                if ampm == "am" and h == 12:
                    h = 0
                cron_expr = f"{mins} {h} * * *"

        # --- Duration (in X minutes / hours / seconds) ---
        duration = 0
        for pattern, multiplier in [
            (r"(\d+)\s*(?:min|minute)", 60),
            (r"(\d+)\s*(?:sec|second)", 1),
            (r"(\d+)\s*(?:hour|hr)", 3600),
        ]:
            m = re.search(pattern, text)
            if m:
                duration += int(m.group(1)) * multiplier

        # --- Extract message ---
        message = "Time's up!"
        m_msg = re.search(
            r"(?:to|that|for)\s+(.+?)(?:\s+in\s+\d|\s+at\s+\d|$)",
            original_text,
            flags=re.IGNORECASE,
        )
        if m_msg:
            message = m_msg.group(1).strip().rstrip(".")
        elif re.search(r"(?:about|for)\s+(.+)$", original_text, flags=re.IGNORECASE):
            message = (
                re.search(r"(?:about|for)\s+(.+)$", original_text, flags=re.IGNORECASE)
                .group(1)
                .strip()
            )
        message = self._strip_calendar_markers(message)

        cid = str(uuid.uuid4())

        if cron_expr:
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO reminders (id, message, cron_expr) VALUES (?, ?, ?)",
                    (cid, message, cron_expr),
                )
            if self._scheduler:
                self._scheduler.schedule_cron(
                    cid, cron_expr, lambda: self._trigger_alert(message, cid)
                )
            calendar_note = ""
            if wants_calendar_sync:
                try:
                    mins, hour = [int(x) for x in cron_expr.split()[:2]]
                    now_local = datetime.now().astimezone()
                    first_start = now_local.replace(
                        hour=hour, minute=mins, second=0, microsecond=0
                    )
                    if first_start <= now_local:
                        first_start += timedelta(days=1)
                    ok, sync_msg = await asyncio.to_thread(
                        self._calendar_create_event_sync,
                        message,
                        first_start,
                        self._calendar_default_duration,
                        True,
                    )
                    calendar_note = (
                        " Added to Google Calendar."
                        if ok
                        else f" Calendar sync skipped ({sync_msg})."
                    )
                except Exception as e:
                    logger.warning(f"Recurring calendar sync failed: {e}")
                    calendar_note = " Calendar sync skipped."
            return f"Got it! I'll remind you to {message} every day.{calendar_note}"

        if duration > 0:
            trigger_time = datetime.now() + timedelta(seconds=duration)
            with self._get_connection() as conn:
                conn.execute(
                    "INSERT INTO reminders (id, message, trigger_time) VALUES (?, ?, ?)",
                    (cid, message, trigger_time.isoformat()),
                )
            if self._scheduler:
                self._scheduler.schedule_once(
                    cid, trigger_time, lambda: self._trigger_alert(message, cid)
                )
            time_str = trigger_time.strftime("%I:%M %p")
            mins = duration // 60
            secs = duration % 60
            human = (
                f"{mins} minute{'s' if mins != 1 else ''}"
                if mins
                else f"{secs} second{'s' if secs != 1 else ''}"
            )
            calendar_note = ""
            if wants_calendar_sync:
                ok, sync_msg = await asyncio.to_thread(
                    self._calendar_create_event_sync,
                    message,
                    trigger_time,
                    self._calendar_default_duration,
                    False,
                )
                calendar_note = (
                    " Added to Google Calendar."
                    if ok
                    else f" Calendar sync skipped ({sync_msg})."
                )
            return f"Reminder set! I'll remind you to {message} in {human} (at {time_str}).{calendar_note}"

        return (
            "I didn't quite catch the time. Try:\n"
            "• 'Remind me in 5 minutes to take my pills'\n"
            "• 'Remind me every day at 9am to drink water'"
        )

    def stop(self):
        if self._scheduler:
            self._scheduler.stop()
