"""PropertyFinder.ae scraper - HTML-based with standard pagination."""

import json
import re
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

PROPERTY_TYPE_SLUGS = {
    "apartment": "apartments",
    "villa": "villas",
    "townhouse": "townhouses",
    "penthouse": "penthouses",
    "duplex": "duplexes",
}


class PropertyFinderScraper(BaseScraper):
    source_name = "propertyfinder"

    def __init__(self, db: Session):
        super().__init__(db)
        self.base_url = "https://www.propertyfinder.ae"

    def _build_url(self, city: str, property_type: str | None = None, page: int = 1) -> str:
        city_slug = CITY_SLUGS.get(city, city)
        if property_type:
            type_slug = PROPERTY_TYPE_SLUGS.get(property_type, property_type)
            url = f"{self.base_url}/en/buy/{city_slug}/{type_slug}-for-sale.html"
        else:
            url = f"{self.base_url}/en/buy/{city_slug}/properties-for-sale.html"
        if page > 1:
            url += f"?page={page}"
        return url

    def _parse_listings(self, html: str, city: str) -> list[dict]:
        """Parse listings from PropertyFinder HTML."""
        soup = BeautifulSoup(html, "lxml")
        listings = []

        # Try JSON-LD structured data first
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                data = json.loads(script.string)
                if isinstance(data, list):
                    for item in data:
                        if item.get("@type") in ("Product", "RealEstateListing", "Residence"):
                            parsed = self._parse_jsonld(item, city)
                            if parsed:
                                listings.append(parsed)
                elif isinstance(data, dict) and data.get("@type") == "ItemList":
                    for item in data.get("itemListElement", []):
                        parsed = self._parse_jsonld(item.get("item", item), city)
                        if parsed:
                            listings.append(parsed)
            except (json.JSONDecodeError, TypeError):
                continue

        if listings:
            return listings

        # Try __NEXT_DATA__
        next_data = soup.find("script", id="__NEXT_DATA__")
        if next_data and next_data.string:
            try:
                data = json.loads(next_data.string)
                page_props = data.get("props", {}).get("pageProps", {})
                # Look for listings in various possible locations
                for key in ["searchResult", "listings", "properties", "results"]:
                    items = page_props.get(key)
                    if isinstance(items, dict):
                        items = items.get("hits", items.get("results", items.get("listings", [])))
                    if isinstance(items, list) and items:
                        for item in items:
                            parsed = self._parse_pf_json(item, city)
                            if parsed:
                                listings.append(parsed)
                        break
            except (json.JSONDecodeError, KeyError):
                pass

        if listings:
            return listings

        # Fallback: parse HTML cards
        cards = soup.select(
            "div[class*='card-list__item'], "
            "article[class*='property'], "
            "div[data-testid='property-card'], "
            "li[class*='listing']"
        )

        if not cards:
            # Broader search
            cards = soup.find_all("a", href=re.compile(r"/en/buy/.+\.html"))

        for card in cards:
            parsed = self._parse_html_card(card, city)
            if parsed:
                listings.append(parsed)

        return listings

    def _parse_jsonld(self, item: dict, city: str) -> dict | None:
        """Parse from JSON-LD structured data."""
        try:
            price = None
            offers = item.get("offers", {})
            if isinstance(offers, dict):
                price = offers.get("price")
            if not price:
                price = item.get("price")
            if not price:
                return None

            url = item.get("url", "")
            source_id = url.rstrip("/").split("/")[-1].replace(".html", "") if url else ""

            return {
                "source_id": source_id or str(item.get("sku", "")),
                "url": url if url.startswith("http") else f"{self.base_url}{url}",
                "title": item.get("name", ""),
                "description": item.get("description", ""),
                "price": float(price),
                "currency": "AED",
                "city": city,
                "neighborhood": "",
                "location_full": "",
            }
        except Exception:
            return None

    def _parse_pf_json(self, item: dict, city: str) -> dict | None:
        """Parse from PropertyFinder's internal JSON data."""
        try:
            price = item.get("price") or item.get("asking_price")
            if isinstance(price, dict):
                price = price.get("value") or price.get("amount")
            if not price:
                return None

            source_id = str(item.get("id") or item.get("reference") or "")
            if not source_id:
                return None

            # Location
            location = item.get("location", {})
            neighborhood = ""
            location_full = ""
            lat, lng = None, None

            if isinstance(location, dict):
                neighborhood = location.get("name", "")
                location_full = location.get("full_name", "")
                lat = location.get("coordinates", {}).get("lat")
                lng = location.get("coordinates", {}).get("lon")
            elif isinstance(location, list):
                parts = [l.get("name", "") for l in location if isinstance(l, dict)]
                neighborhood = parts[-1] if parts else ""
                location_full = " > ".join(parts)

            url = item.get("url") or item.get("links", {}).get("detail", "")
            if url and not url.startswith("http"):
                url = f"{self.base_url}{url}"

            listed_date = None
            created = item.get("created_at") or item.get("publishedAt")
            if created:
                try:
                    listed_date = datetime.fromisoformat(str(created).replace("Z", "+00:00"))
                except (ValueError, AttributeError):
                    pass

            return {
                "source_id": source_id,
                "url": url,
                "title": item.get("title") or item.get("name", ""),
                "description": item.get("description", ""),
                "price": float(price),
                "currency": "AED",
                "property_type": item.get("type", {}).get("slug", "")
                    if isinstance(item.get("type"), dict)
                    else str(item.get("propertyType", "")),
                "bedrooms": item.get("bedrooms") or item.get("bedroom"),
                "bathrooms": item.get("bathrooms") or item.get("bathroom"),
                "area_sqft": float(item["size"]) if item.get("size") else None,
                "city": city,
                "neighborhood": neighborhood,
                "location_full": location_full,
                "latitude": lat,
                "longitude": lng,
                "furnishing": item.get("furnishing"),
                "completion_status": item.get("completionStatus") or item.get("completion_status"),
                "listed_date": listed_date,
            }
        except Exception as e:
            logger.debug(f"[propertyfinder] Parse error: {e}")
            return None

    def _parse_html_card(self, card, city: str) -> dict | None:
        """Parse a listing from an HTML card element."""
        try:
            # Find link
            if card.name == "a":
                link = card
            else:
                link = card.find("a", href=True)

            if not link:
                return None

            url = link.get("href", "")
            if not url or "/buy/" not in url:
                return None
            if not url.startswith("http"):
                url = f"{self.base_url}{url}"

            # Title
            title_el = card.find(["h2", "h3", "h4"])
            title = title_el.get_text(strip=True) if title_el else ""

            # Price
            price = None
            text = card.get_text()
            price_match = re.search(r"AED\s*([\d,]+)", text)
            if not price_match:
                price_match = re.search(r"([\d,]+)\s*AED", text)
            if price_match:
                try:
                    price = float(price_match.group(1).replace(",", ""))
                except ValueError:
                    pass

            if not price:
                return None

            # Source ID from URL
            source_id = url.rstrip("/").split("/")[-1].replace(".html", "").split("-")[-1]

            # Try to extract bedrooms/bathrooms from text
            bedrooms = None
            bed_match = re.search(r"(\d+)\s*(?:bed|BR|bedroom)", text, re.IGNORECASE)
            if bed_match:
                bedrooms = int(bed_match.group(1))

            bathrooms = None
            bath_match = re.search(r"(\d+)\s*(?:bath|BA|bathroom)", text, re.IGNORECASE)
            if bath_match:
                bathrooms = int(bath_match.group(1))

            # Area
            area = None
            area_match = re.search(r"([\d,]+)\s*(?:sq\.?\s*ft|sqft)", text, re.IGNORECASE)
            if area_match:
                try:
                    area = float(area_match.group(1).replace(",", ""))
                except ValueError:
                    pass

            return {
                "source_id": source_id,
                "url": url,
                "title": title,
                "price": price,
                "currency": "AED",
                "bedrooms": bedrooms,
                "bathrooms": bathrooms,
                "area_sqft": area,
                "city": city,
                "neighborhood": "",
                "location_full": "",
            }
        except Exception:
            return None

    async def scrape(self, city: str, max_pages: int = 10) -> int:
        total_saved = 0

        for page in range(1, max_pages + 1):
            url = self._build_url(city, page=page)
            logger.info(f"[propertyfinder] Fetching page {page}: {url}")

            resp = await self.fetch(url)
            if not resp:
                logger.warning(f"[propertyfinder] No response for page {page}, stopping")
                break

            parsed = self._parse_listings(resp.text, city)
            saved = self.save_properties(parsed)
            total_saved += saved

            if saved == 0:
                logger.info(f"[propertyfinder] No listings on page {page}, stopping")
                break

        return total_saved
