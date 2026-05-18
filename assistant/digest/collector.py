"""
Morning Digest System
Collects data from various sources and creates a daily briefing.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class DigestItem:
    source: str
    title: str
    content: str
    priority: str = "normal"


@dataclass
class DailyDigest:
    date: str
    weather: str | None = None
    calendar_events: list[DigestItem] = None
    emails: list[DigestItem] = None
    news: list[DigestItem] = None
    custom: list[DigestItem] = None

    def __post_init__(self):
        if self.calendar_events is None:
            self.calendar_events = []
        if self.emails is None:
            self.emails = []
        if self.news is None:
            self.news = []
        if self.custom is None:
            self.custom = []


class DigestCollector:
    """Collects data from various sources for the morning digest."""

    def __init__(
        self,
        gmail_client=None,
        calendar_client=None,
        weather_client=None,
        news_client=None,
    ):
        self.gmail = gmail_client
        self.calendar = calendar_client
        self.weather = weather_client
        self.news = news_client

    async def collect(self) -> DailyDigest:
        from datetime import datetime

        today = datetime.now().strftime("%Y-%m-%d")

        digest = DailyDigest(date=today)

        if self.weather:
            try:
                weather_data = await self._get_weather()
                digest.weather = weather_data
            except Exception as e:
                logger.error(f"Weather fetch error: {e}")

        if self.calendar:
            try:
                events = await self._get_calendar(today)
                digest.calendar_events = events
            except Exception as e:
                logger.error(f"Calendar fetch error: {e}")

        if self.gmail:
            try:
                emails = await self._get_emails()
                digest.emails = emails
            except Exception as e:
                logger.error(f"Gmail fetch error: {e}")

        if self.news:
            try:
                news_items = await self._get_news()
                digest.news = news_items
            except Exception as e:
                logger.error(f"News fetch error: {e}")

        return digest

    async def _get_weather(self) -> str:
        result = await self.weather.execute()
        if result.success:
            return str(result.result)
        return "Weather unavailable"

    async def _get_calendar(self, date: str) -> list[DigestItem]:
        return []

    async def _get_emails(self) -> list[DigestItem]:
        return []

    async def _get_news(self) -> list[DigestItem]:
        return []
