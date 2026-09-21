"""
Calendar Skill - Google Calendar integration
"""

import datetime
import logging
import os.path
from typing import Any

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from skills.base_skill import BaseSkill, skill

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/calendar"]
CACHE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache"
)


@skill(
    name="calendar",
    keywords=["calendar", "schedule", "events", "meeting", "appointment", "agenda"],
    description="Manage your Google Calendar: list events and create new meetings with conflict detection",
    priority=6,
    requires_internet=True,
    parameters={
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list", "create", "check_conflicts"],
                "description": "The action to perform on the calendar",
            },
            "summary": {
                "type": "string",
                "description": "Brief description of the event (required for create)",
            },
            "start_time": {
                "type": "string",
                "description": "ISO format start time (e.g., 2026-02-17T15:00:00)",
            },
            "duration_minutes": {
                "type": "integer",
                "description": "Duration of the event in minutes",
                "default": 30,
            },
        },
        "required": ["action"],
    },
)
class CalendarSkill(BaseSkill):
    """
    Enhanced Calendar Skill with Creation and Conflict Detection.
    """

    def __init__(self):
        super().__init__()
        self.creds = None
        self.service = None
        self._auth_completed = False

        # Try to authenticate on startup (silently)
        try:
            self._authenticate(interactive=False)
        except Exception:
            pass

    def _authenticate(self, interactive=True):
        """Authenticate with Google Calendar API"""
        token_path = os.path.join(CACHE_DIR, "token.json")
        creds_path = "credentials.json"

        if os.path.exists(token_path):
            self.creds = Credentials.from_authorized_user_file(token_path, SCOPES)

        if not self.creds or not self.creds.valid:
            if self.creds and self.creds.expired and self.creds.refresh_token:
                self.creds.refresh(Request())
            else:
                if not interactive:
                    return  # Skip silent fail

                if not os.path.exists(creds_path):
                    raise FileNotFoundError(
                        "credentials.json not found. Please download it from Google Cloud Console."
                    )

                flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
                self.creds = flow.run_local_server(port=0)

            with open(token_path, "w") as token:
                token.write(self.creds.to_json())

        self.service = build("calendar", "v3", credentials=self.creds)
        self._auth_completed = True
        logger.info("✅ Google Calendar connected")

    async def handle_tool_call(self, args: dict, context: Any) -> str:
        """Handle structured tool calls from LLM."""
        if not self._auth_completed:
            return "Calendar is not authenticated. Please run the assistant interactively to sign in."

        action = args.get("action")
        if action == "list":
            return self._list_events()
        elif action == "create":
            summary = args.get("summary")
            start_str = args.get("start_time")
            duration = args.get("duration_minutes", 30)
            if not summary or not start_str:
                return "I need a summary and start time to create an event."
            return await self._create_event(summary, start_str, duration)

        return "Unknown calendar action."

    async def handle(self, text: str, context: dict[str, Any]) -> str:
        """Fallback handle for direct keyword triggers."""
        if not self._auth_completed:
            return "I need to authenticate your Google Calendar. Please check your terminal for the login link."

        text_lower = text.lower()

        if any(k in text_lower for k in ["what", "list", "show", "agenda"]):
            return self._list_events()

        if any(k in text_lower for k in ["create", "add", "schedule"]):
            return "I can help you schedule that. What's the meeting about and when should it start?"

        return "I can manage your calendar. Try asking 'What's on my agenda?' or 'Schedule a meeting for tomorrow at 2pm'."

    def _list_events(self) -> str:
        """List next 5 upcoming events"""
        try:
            now = datetime.datetime.now(datetime.UTC).isoformat()
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=now,
                    maxResults=5,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            if not events:
                return "No upcoming events found on your calendar."

            response = "Here are your next 5 events: "
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                try:
                    dt = datetime.datetime.fromisoformat(start.replace("Z", "+00:00"))
                    time_str = dt.strftime("%A at %I:%M %p")
                except (ValueError, AttributeError):
                    time_str = start

                response += f"{event['summary']} on {time_str}. "

            return response

        except Exception as e:
            logger.error(f"Calendar list error: {e}")
            return "I had trouble checking your calendar."

    async def _create_event(
        self, summary: str, start_time_str: str, duration_minutes: int
    ) -> str:
        """Create a calendar event with conflict detection."""
        try:
            # Parse start time
            start_dt = datetime.datetime.fromisoformat(start_time_str)
            end_dt = start_dt + datetime.timedelta(minutes=duration_minutes)

            # 1. Check for conflicts
            conflicts = self._check_conflicts(start_dt, end_dt)
            if conflicts:
                return f"Conflict detected! You already have '{conflicts[0]}' scheduled during that time. Should I schedule it anyway?"

            # 2. Create event
            event = {
                "summary": summary,
                "start": {"dateTime": start_dt.isoformat(), "timeZone": "UTC"},
                "end": {"dateTime": end_dt.isoformat(), "timeZone": "UTC"},
            }

            self.service.events().insert(calendarId="primary", body=event).execute()
            return f"Meeting '{summary}' has been successfully scheduled for {start_dt.strftime('%A at %I:%M %p')}."

        except Exception as e:
            logger.error(f"Calendar create error: {e}")
            return f"Failed to create event: {e}"

    def _check_conflicts(
        self, start_dt: datetime.datetime, end_dt: datetime.datetime
    ) -> list[str]:
        """Check for overlapping events."""
        try:
            # Buffer window
            events_result = (
                self.service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_dt.isoformat() + "Z",
                    timeMax=end_dt.isoformat() + "Z",
                    singleEvents=True,
                )
                .execute()
            )

            events = events_result.get("items", [])
            return [e["summary"] for e in events]
        except Exception:
            return []
