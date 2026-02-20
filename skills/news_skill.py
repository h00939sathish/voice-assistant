import asyncio
from typing import List, Dict

class NewsSkill:
    """Skill for fetching latest news headlines"""
    
    def __init__(self):
        # In a real scenario, this would use a News API key
        # For now, we'll use a public RSS-to-JSON or a mock response
        self.api_url = "https://news.google.com/rss"

    async def get_headlines(self, category: str = "general") -> List[Dict[str, str]]:
        """Fetch latest headlines for a category"""
        print(f"📰 Fetching {category} news...")
        
        # Mock data for demonstration if no API key is provided
        # This ensures the tool works immediately
        return [
            {
                "title": f"New breakthrough in {category} announced today",
                "source": "Global News",
                "url": "https://example.com/news1"
            },
            {
                "title": f"Top experts discuss the future of {category}",
                "source": "Tech Daily",
                "url": "https://example.com/news2"
            },
            {
                "title": f"Market trends show shift in {category} sector",
                "source": "Business Weekly",
                "url": "https://example.com/news3"
            }
        ]

if __name__ == "__main__":
    skill = NewsSkill()
    loop = asyncio.get_event_loop()
    news = loop.run_until_complete(skill.get_headlines())
    print(news)
