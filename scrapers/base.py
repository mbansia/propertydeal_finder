import asyncio
import logging
from abc import ABC, abstractmethod
from datetime import datetime

import httpx
from sqlalchemy.orm import Session
from sqlalchemy.dialects.sqlite import insert as sqlite_upsert

from database.models import Property
from config import settings

logger = logging.getLogger(__name__)

# Realistic browser headers
DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
}


class BaseScraper(ABC):
    """Base scraper with rate limiting and database upsert logic."""

    source_name: str = ""

    def __init__(self, db: Session):
        self.db = db
        self.delay = settings.request_delay_seconds
        self.client = httpx.AsyncClient(
            headers=DEFAULT_HEADERS,
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self):
        await self.client.aclose()

    async def fetch(self, url: str, **kwargs) -> httpx.Response | None:
        """Fetch a URL with rate limiting and error handling."""
        await asyncio.sleep(self.delay)
        try:
            resp = await self.client.get(url, **kwargs)
            resp.raise_for_status()
            return resp
        except httpx.HTTPStatusError as e:
            logger.warning(f"[{self.source_name}] HTTP {e.response.status_code} for {url}")
            return None
        except httpx.RequestError as e:
            logger.warning(f"[{self.source_name}] Request error for {url}: {e}")
            return None

    async def fetch_json(self, url: str, **kwargs) -> dict | None:
        """Fetch and parse JSON."""
        resp = await self.fetch(url, **kwargs)
        if resp:
            try:
                return resp.json()
            except Exception:
                logger.warning(f"[{self.source_name}] Failed to parse JSON from {url}")
        return None

    def save_properties(self, listings: list[dict]) -> int:
        """Upsert a batch of parsed property dicts into the database."""
        saved = 0
        for item in listings:
            if not item.get("source_id") or not item.get("price"):
                continue

            # Calculate price per sqft
            if item.get("area_sqft") and item["area_sqft"] > 0:
                item["price_per_sqft"] = round(item["price"] / item["area_sqft"], 2)

            item["source"] = self.source_name
            item["scraped_at"] = datetime.utcnow()
            item["updated_at"] = datetime.utcnow()
            item["is_active"] = True

            # Upsert: insert or update on conflict
            stmt = sqlite_upsert(Property).values(**item)
            stmt = stmt.on_conflict_do_update(
                index_elements=["source", "source_id"],
                set_={
                    "price": item.get("price"),
                    "title": item.get("title"),
                    "price_per_sqft": item.get("price_per_sqft"),
                    "updated_at": datetime.utcnow(),
                    "is_active": True,
                },
            )
            self.db.execute(stmt)
            saved += 1

        self.db.commit()
        logger.info(f"[{self.source_name}] Saved {saved} properties")
        return saved

    @abstractmethod
    async def scrape(self, city: str, max_pages: int = 10) -> int:
        """Scrape listings for a city. Returns count of properties saved."""
        ...

    async def scrape_all(self, max_pages: int = 10) -> int:
        """Scrape all configured cities."""
        total = 0
        for city in settings.cities:
            logger.info(f"[{self.source_name}] Scraping {city}...")
            count = await self.scrape(city, max_pages=max_pages)
            total += count
            logger.info(f"[{self.source_name}] {city}: {count} listings")
        return total
