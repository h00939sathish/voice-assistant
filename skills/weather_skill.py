"""
Weather Skill - Fetches real-time weather via Open-Meteo API.
"""

import datetime
import sqlite3
from pathlib import Path
from typing import Any

import aiohttp

from skills.base_skill import BaseSkill, skill

CACHE_DIR = Path(__file__).parent.parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)
DB_PATH = CACHE_DIR / "weather_cache.db"


@skill(
    name="weather",
    keywords=[
        "weather",
        "temperature",
        "forecast",
        "rain",
        "sunny",
        "wind",
        "hot",
        "cold",
        "forecast",
        "snow",
    ],
    description="Gets current weather, 7-day forecast, and alerts for any city",
    priority=5,
    requires_internet=True,
    parameters={
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "The city name to get weather for (e.g. London, New York)",
            },
            "days": {
                "type": "integer",
                "description": "Number of days for forecast (1-7)",
                "default": 1,
            },
        },
        "required": ["city"],
    },
)
class WeatherSkill(BaseSkill):
    """Enhanced Weather Skill with Geocoding and Caching."""

    def __init__(self):
        super().__init__()
        self._init_db()

    def _init_db(self):
        """Initialize the location cache database."""
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS location_cache (
                    city TEXT PRIMARY KEY,
                    lat REAL,
                    lon REAL,
                    display_name TEXT,
                    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)

    async def _get_coordinates(self, city: str) -> tuple[float, float, str] | None:
        """Get lat/lon from cache or Nominatim geocoding."""
        if not city:
            return None
        city_clean = city.lower().strip()

        # 1. Check cache
        with sqlite3.connect(DB_PATH) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM location_cache WHERE city = ?", (city_clean,)
            ).fetchone()
            if row:
                # Cache for 30 days
                updated_at = datetime.datetime.fromisoformat(row["updated_at"])
                if (datetime.datetime.now() - updated_at).days < 30:
                    return row["lat"], row["lon"], row["display_name"]

        # 2. Geocode via Nominatim
        url = f"https://nominatim.openstreetmap.org/search?q={city_clean}&format=json&limit=1"
        headers = {"User-Agent": "BuddyVoiceAssistant/1.0"}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=5) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        if data:
                            lat, lon = float(data[0]["lat"]), float(data[0]["lon"])
                            display_name = data[0]["display_name"]

                            # Update cache
                            with sqlite3.connect(DB_PATH) as conn:
                                conn.execute(
                                    """
                                    INSERT OR REPLACE INTO location_cache (city, lat, lon, display_name, updated_at)
                                    VALUES (?, ?, ?, ?, ?)
                                """,
                                    (
                                        city_clean,
                                        lat,
                                        lon,
                                        display_name,
                                        datetime.datetime.now().isoformat(),
                                    ),
                                )

                            return lat, lon, display_name
        except Exception as e:
            print(f"   [!] Geocoding error: {e}")

        return None

    async def handle_tool_call(self, args: dict, context: Any) -> str:
        city = args.get("city")
        # Fallback: extract city from context text if not in args
        if not city and context:
            text = context.get("text", "")
            if text:
                for token in text.split():
                    if token.lower() not in [
                        "what",
                        "is",
                        "the",
                        "weather",
                        "in",
                        "for",
                        "today",
                        "tomorrow",
                        "forecast",
                    ]:
                        if len(token) > 2 or token.istitle():
                            city = token
                            break
        if not city:
            return "Please provide a city name for weather (e.g., 'weather in Chennai')"
        days = args.get("days", 1)
        return await self._process_weather(city, days)

    async def handle(self, text: str, context: Any) -> str | None:
        # Simple extraction for direct handle call
        city = None
        for token in text.split():
            if token.istitle():
                city = token
                break

        if not city:
            city = self.config.get("default_location", "London")

        days = 3 if "forecast" in text.lower() or "next week" in text.lower() else 1
        return await self._process_weather(city, days)

    async def _process_weather(self, city: str, days: int = 1) -> str:
        """Core weather processing logic."""
        coords = await self._get_coordinates(city)
        if not coords:
            return f"I couldn't find the location for '{city}'. Please check the name and try again."

        lat, lon, display_name = coords
        try:
            data = await self.get_weather_data(lat, lon, days)
            return self.format_weather_v2(display_name, data, days)
        except Exception as e:
            return f"I had trouble getting the weather data for {city}. ({e})"

    async def get_weather_data(self, lat: float, lon: float, days: int) -> dict:
        """Fetch comprehensive weather data from Open-Meteo."""
        units = self.config.get("units", "celsius")
        url = (
            f"https://api.open-meteo.com/v1/forecast?"
            f"latitude={lat}&longitude={lon}"
            f"&current_weather=true"
            f"&daily=temperature_2m_max,temperature_2m_min,precipitation_sum,weathercode"
            f"&temperature_unit={units}"
            f"&timezone=auto"
            f"&forecast_days={max(1, min(7, days))}"
        )

        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=5) as resp:
                if resp.status != 200:
                    raise RuntimeError(f"Weather API status {resp.status}")
                return await resp.json()

    def format_weather_v2(self, location: str, data: dict, days: int) -> str:
        """Enhanced formatting for v2 weather output."""
        try:
            current = data["current_weather"]
            temp = current.get("temperature")
            units = "°C" if self.config.get("units", "celsius") == "celsius" else "°F"

            city_short = location.split(",")[0]
            summary = f"In {city_short}, it's currently {temp}{units}. "

            if days > 1 and "daily" in data:
                summary += f"Here is the {days}-day forecast: "
                daily = data["daily"]
                for i in range(days):
                    date_dt = datetime.datetime.fromisoformat(daily["time"][i])
                    day_name = "Today" if i == 0 else date_dt.strftime("%A")
                    hi = daily["temperature_2m_max"][i]
                    lo = daily["temperature_2m_min"][i]
                    summary += f"{day_name}: {hi}/{lo}{units}. "
            else:
                # Today's detail
                daily = data["daily"]
                hi = daily["temperature_2m_max"][0]
                lo = daily["temperature_2m_min"][0]
                rain = daily["precipitation_sum"][0]
                summary += f"Today's high is {hi}{units} and low is {lo}{units}. "
                if rain > 0:
                    summary += f"Expect about {rain}mm of rain."

            return summary
        except Exception:
            return f"Weather data for {location} is currently unavailable."
