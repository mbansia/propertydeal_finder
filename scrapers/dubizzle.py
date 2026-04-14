"""Dubizzle.com scraper - targets the search API used by the frontend."""

import json
import logging
from datetime import datetime

from bs4 import BeautifulSoup
from sqlalchemy.orm import Session

from scrapers.base import BaseScraper

logger = logging.getLogger(__name__)

CITY_SUBDOMAINS = {
    "dubai": "dubai",
    "abu-dhabi": "abudhabi",
}

PROPERTY_TYPE_SLUGS = {
    "apartment": "apartmentflat",
    "villa": "villahouse",
    "townhouse": "townhouse",
    "penthouse": "penthouse",
    "duplex": "duplex",
}


class DubizzleScraper(BaseScraper):
    source_name = "dubizzle"

    def __init__(self, db: Session):
        super().__init__(db)
        self.base_url = "https://{city}.dubizzle.com"

    def _build_url(self, city: str, property_type: str | None = None, page: int = 1) -> str:
        city_sub = CITY_SUBDOMAINS.get(city, city)
        base = self.base_url.format(city=city_sub)

        if property_type:
            type_slug = PROPERTY_TYPE_SLUGS.get(property_type, property_type)
            url = f"{base}/en/property-for-sale/residential/{type_slug}/"
        else:
            url = f"{base}/en/property-for-sale/residential/"

        if page > 1:
            url += f"?page={page}"
        return url

    def _parse_listings_from_html(self, html: str, city: str) -> list[dict]:
        """Parse listings from Dubizzle HTML/embedded JSON."""
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Try to find embedded JSON data (Next.js or similar)
        for script in soup.find_all("script"):
            text = script.string or ""
            if "window.__NEXT_DATA__" in text or '"listings"' in text or '"results"' in text:
                try:
                    # Extract JSON from script
                    start = text.find("{")
                    end = text.rfind("}") + 1
                    if start >= 0 and end > start:
                        data = json.loads(text[start:end])
                        items = self._extract_items_from_json(data)
                        for item in items:
                            parsed = self._parse_json_listing(item, city)
                            if parsed:
                                listings.append(parsed)
                except (json.JSONDecodeError, KeyError):
                    continue

        if listings:
            return listings

        # Try __NEXT_DATA__ script tag
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                page_props = data.get("props", {}).get("pageProps", {})
                items = self._extract_items_from_json(page_props)
                for item in items:
                    parsed = self._parse_json_listing(item, city)
                    if parsed:
                        listings.append(parsed)
            except (json.JSONDecodeError, KeyError):
                pass

        if listings:
            return listings

        # Fallback: parse HTML listing cards
        cards = soup.select("a[data-testid='listing-card'], div[class*='listing'], article")
        for card in cards:
            try:
                parsed = self._parse_html_card(card, city)
                if parsed:
                    listings.append(parsed)
            except Exception:
                continue

        return listings

    def _extract_items_from_json(self, data: dict, depth: int = 0) -> list[dict]:
        """Recursively find listing arrays in nested JSON."""
        if depth > 5:
            return []

        items = []
        if isinstance(data, list):
            return data

        if isinstance(data, dict):
            # Check common keys for listing arrays
            for key in ["results", "hits", "listings", "items", "ads", "data", "searchResults"]:
                val = data.get(key)
                if isinstance(val, list) and len(val) > 0:
                    # Check if items look like property listings
                    first = val[0]
                    if isinstance(first, dict) and any(
                        k in first for k in ["price", "title", "id", "name", "details"]
                    ):
                        return val

            # Recurse one level
            for val in data.values():
                if isinstance(val, (dict, list)):
                    result = self._extract_items_from_json(val, depth + 1)
                    if result:
                        return result

        return items

    def _parse_json_listing(self, item: dict, city: str) -> dict | None:
        """Parse a listing from Dubizzle's JSON data."""
        try:
            price = item.get("price") or item.get("details", {}).get("price")
            if isinstance(price, dict):
                price = price.get("value") or price.get("amount")
            if not price:
                return None

            source_id = str(
                item.get("id") or item.get("externalID") or item.get("adId") or ""
            )
            if not source_id:
                return None

            # Location
            location = item.get("location", {})
            neighborhood = ""
            location_full = ""
            lat, lng = None, None

            if isinstance(location, dict):
                neighborhood = location.get("name", "")
                location_full = location.get("full_name", neighborhood)
                lat = location.get("lat") or location.get("latitude")
                lng = location.get("lng") or location.get("longitude")
            elif isinstance(location, list) and location:
                neighborhood = location[-1].get("name", "") if location else ""
                location_full = " > ".join(l.get("name", "") for l in location)

            # Details
            details = item.get("details", {})
            bedrooms = item.get("rooms") or item.get("bedrooms") or details.get("bedrooms")
            bathrooms = item.get("baths") or item.get("bathrooms") or details.get("bathrooms")
            area = item.get("area") or item.get("size") or details.get("size")

            if isinstance(bedrooms, str):
                try:
                    bedrooms = int(bedrooms)
                except ValueError:
                    bedrooms = None

            listed_date = None
            created = item.get("createdAt") or item.get("created_at") or item.get("postedDate")
            if created:
                try:
                    listed_date = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            url = item.get("url") or item.get("absolute_url", "")
            if url and not url.startswith("http"):
                city_sub = CITY_SUBDOMAINS.get(city, city)
                url = f"https://{city_sub}.dubizzle.com{url}"

            return {
                "source_id": source_id,
                "url": url,
                "title": item.get("title") or item.get("name", ""),
                "description": item.get("description", ""),
                "price": float(price),
                "currency": "AED",
                "property_type": item.get("category", {}).get("slug", "")
                    if isinstance(item.get("category"), dict)
                    else str(item.get("type", "")),
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "area_sqft": float(area) if area else None,
                "city": city,
                "neighborhood": neighborhood,
                "location_full": location_full,
                "latitude": lat,
                "longitude": lng,
                "furnishing": item.get("furnishing") or details.get("furnishing"),
                "completion_status": item.get("completionStatus"),
                "listed_date": listed_date,
            }
        except Exception as e:
            logger.debug(f"[dubizzle] Parse error: {e}")
            return None

    def _parse_html_card(self, card, city: str) -> dict | None:
        """Fallback: parse a listing from an HTML card element."""
        link = card.find("a", href=True)
        if not link:
            if card.name == "a" and card.get("href"):
                link = card
            else:
                return None

        url = link.get("href", "")
        if not url:
            return None
        if not url.startswith("http"):
            city_sub = CITY_SUBDOMAINS.get(city, city)
            url = f"https://{city_sub}.dubizzle.com{url}"

        title_el = card.find(["h2", "h3", "span"])
        title = title_el.get_text(strip=True) if title_el else ""

        # Extract price
        price = None
        price_el = card.find(string=lambda t: t and ("AED" in str(t) or "aed" in str(t).lower()))
        if price_el:
            import re
            nums = re.findall(r"[\d,]+", str(price_el).replace("AED", ""))
            if nums:
                try:
                    price = float(nums[0].replace(",", ""))
                except ValueError:
                    pass

        if not price:
            return None

        source_id = url.rstrip("/").split("/")[-1].split("-")[-1]

        return {
            "source_id": source_id or url,
            "url": url,
            "title": title,
            "price": price,
            "currency": "AED",
            "city": city,
            "neighborhood": "",
            "location_full": "",
        }

    async def scrape(self, city: str, max_pages: int = 10) -> int:
        total_saved = 0

        for page in range(1, max_pages + 1):
            url = self._build_url(city, page=page)
            logger.info(f"[dubizzle] Fetching page {page}: {url}")

            resp = await self.fetch(url)
            if not resp:
                logger.warning(f"[dubizzle] No response for page {page}, stopping")
                break

            parsed = self._parse_listings_from_html(resp.text, city)
            saved = self.save_properties(parsed)
            total_saved += saved

            if saved == 0:
                logger.info(f"[dubizzle] No listings on page {page}, stopping")
                break

        return total_saved
