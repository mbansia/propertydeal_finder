"""Bayut.com scraper - extracts listing data from __NEXT_DATA__ JSON embedded in pages."""

import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

CITY_SLUGS = {
    "dubai": "dubai",
    "abu-dhabi": "abu-dhabi",
}

PROPERTY_TYPES = {
    "apartment": "apartments",
    "villa": "villas",
    "townhouse": "townhouses",
    "penthouse": "penthouses",
    "duplex": "duplexes",
}


class BayutScraper(BaseScraper):
    source_name = "bayut"

    def __init__(self, db: Session):
        super().__init__(db)
        self.base_url = "https://www.bayut.com"

    def _build_url(self, city: str, property_type: str | None = None, page: int = 1) -> str:
        city_slug = CITY_SLUGS.get(city, city)
        if property_type:
            type_slug = PROPERTY_TYPES.get(property_type, property_type)
            url = f"{self.base_url}/for-sale/{type_slug}/{city_slug}/"
        else:
            url = f"{self.base_url}/for-sale/property/{city_slug}/"
        if page > 1:
            url += f"?page={page}"
        return url

    def _parse_next_data(self, html: str) -> list[dict]:
        """Extract listings from __NEXT_DATA__ script tag."""
        soup = BeautifulSoup(html, "lxml")
        script_tag = soup.find("script", id="__NEXT_DATA__")
        if not script_tag:
            return []

        try:
            data = json.loads(script_tag.string)
        except (json.JSONDecodeError, TypeError):
            logger.warning("[bayut] Failed to parse __NEXT_DATA__")
            return []

        # Navigate the Next.js data structure to find listings
        props = data.get("props", {}).get("pageProps", {})

        # Try different possible keys for the search results
        hits = []
        for key in ["searchResult", "properties", "hits"]:
            if key in props:
                result = props[key]
                if isinstance(result, dict):
                    hits = result.get("hits", result.get("results", []))
                elif isinstance(result, list):
                    hits = result
                if hits:
                    break

        return hits

    def _parse_listing(self, item: dict, city: str) -> dict | None:
        """Parse a single listing from Bayut's data structure."""
        try:
            # Bayut uses nested structure for location
            location_parts = []
            location = item.get("location", [])
            if isinstance(location, list):
                location_parts = [loc.get("name", "") for loc in location if loc.get("name")]

            neighborhood = ""
            if len(location_parts) >= 2:
                neighborhood = location_parts[-2]  # Second to last is usually neighborhood
            elif len(location_parts) == 1:
                neighborhood = location_parts[0]

            # Extract area
            area = item.get("area")
            area_sqft = None
            if area:
                area_sqft = area if isinstance(area, (int, float)) else None

            # Some listings have area in sqft directly
            if not area_sqft:
                area_sqft = item.get("areaSqFt") or item.get("size")

            price = item.get("price")
            if not price:
                return None

            # Parse date
            listed_date = None
            added_on = item.get("createdAt") or item.get("addedOn")
            if added_on:
                try:
                    listed_date = datetime.fromisoformat(added_on.replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            return {
                "source_id": str(item.get("id") or item.get("externalID", "")),
                "url": f"{self.base_url}{item.get('slug', '')}",
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "price": float(price),
                "currency": "AED",
                "property_type": (item.get("category", [{}])[0].get("slug", "")
                                  if isinstance(item.get("category"), list)
                                  else item.get("categorySlug", "")),
                "bedrooms": item.get("rooms") or item.get("bedrooms"),
                "bathrooms": item.get("baths") or item.get("bathrooms"),
                "area_sqft": float(area_sqft) if area_sqft else None,
                "city": city,
                "neighborhood": neighborhood,
                "location_full": " > ".join(location_parts) if location_parts else "",
                "latitude": item.get("geography", {}).get("lat") if isinstance(item.get("geography"), dict) else None,
                "longitude": item.get("geography", {}).get("lng") if isinstance(item.get("geography"), dict) else None,
                "furnishing": item.get("furnishingStatus"),
                "completion_status": item.get("completionStatus"),
                "listed_date": listed_date,
            }
        except Exception as e:
            logger.debug(f"[bayut] Failed to parse listing: {e}")
            return None

    def _parse_html_fallback(self, html: str, city: str) -> list[dict]:
        """Fallback: parse listings from HTML if __NEXT_DATA__ fails."""
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Look for listing cards by common attribute patterns
        cards = soup.select("article[role='group'], div[data-testid='listing-card'], li[aria-label]")
        if not cards:
            cards = soup.find_all("article")

        for card in cards:
            try:
                link = card.find("a", href=True)
                url = link["href"] if link else ""
                if url and not url.startswith("http"):
                    url = self.base_url + url

                title_el = card.find(["h2", "h3"])
                title = title_el.get_text(strip=True) if title_el else ""

                # Extract price - look for AED or numeric patterns
                price_el = card.find(string=lambda t: t and "AED" in str(t))
                price = None
                if price_el:
                    price_text = str(price_el).replace("AED", "").replace(",", "").strip()
                    try:
                        price = float(price_text)
                    except ValueError:
                        pass

                if not price or not url:
                    continue

                # Extract source ID from URL
                source_id = url.rstrip("/").split("-")[-1].replace(".html", "")

                listings.append({
                    "source_id": source_id,
                    "url": url,
                    "title": title,
                    "price": price,
                    "currency": "AED",
                    "city": city,
                    "neighborhood": "",
                    "location_full": "",
                })
            except Exception:
                continue

        return listings

    async def scrape(self, city: str, max_pages: int = 10) -> int:
        total_saved = 0

        for page in range(1, max_pages + 1):
            url = self._build_url(city, page=page)
            logger.info(f"[bayut] Fetching page {page}: {url}")

            resp = await self.fetch(url)
            if not resp:
                logger.warning(f"[bayut] No response for page {page}, stopping")
                break

            html = resp.text

            # Try __NEXT_DATA__ first
            raw_listings = self._parse_next_data(html)

            if raw_listings:
                parsed = []
                for item in raw_listings:
                    listing = self._parse_listing(item, city)
                    if listing:
                        parsed.append(listing)
                saved = self.save_properties(parsed)
            else:
                # Fallback to HTML parsing
                parsed = self._parse_html_fallback(html, city)
                saved = self.save_properties(parsed)

            total_saved += saved

            if saved == 0:
                logger.info(f"[bayut] No listings on page {page}, stopping")
                break

        return total_saved
