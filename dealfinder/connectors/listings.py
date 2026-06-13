"""Listing connectors: Bayut, Dubizzle, Property Finder, Reddit.

These produce *asking prices*. The three portals block plain HTTP clients, so we
scrape them with a headless browser (see `browser.py`). All three are Next.js
apps that ship their search results as JSON inside a `__NEXT_DATA__` script tag —
we parse that rather than fragile CSS selectors, which is far more stable.

Field paths can drift when a site redeploys. Each scraper has a `debug_dump()`
to save the raw `__NEXT_DATA__` so you can re-check the mapping, and the parsing
is deliberately defensive (try several likely keys, skip rows that don't parse).

Reddit reads its public JSON directly (no browser needed); treat its rows as
leads to verify, since posts are free text.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pandas as pd
import requests

from .base import ListingConnector
from .browser import BrowserSession, BrowseConfig

SQM_TO_SQFT = 10.7639


# ── helpers ──────────────────────────────────────────────────────────────────
def _first(d: dict, *keys, default=None):
    """Return the first present, non-null value among keys (supports a.b paths)."""
    for k in keys:
        cur = d
        ok = True
        for part in k.split("."):
            if isinstance(cur, dict) and part in cur and cur[part] is not None:
                cur = cur[part]
            else:
                ok = False
                break
        if ok:
            return cur
    return default


def _canon_type(val) -> str | None:
    """Normalize a source's type label to the engine's vocabulary.

    Listings and transaction comps must share property_type spelling/casing or
    the benchmark lookup misses. Portals say "Apartments"/"Villa"; we use the
    lowercase singular the rest of the pipeline expects.
    """
    if not val:
        return None
    s = str(val).lower()
    if "penthouse" in s:
        return "penthouse"
    if "town" in s:  # "townhouse" / "town house"
        return "townhouse"
    if "villa" in s:
        return "villa"
    if "apart" in s or "flat" in s:
        return "apartment"
    return s.rstrip("s")


def _to_beds(val) -> int | None:
    if val is None:
        return None
    s = str(val).strip().lower()
    if s in {"studio", "0"}:
        return 0
    m = re.search(r"\d+", s)
    return int(m.group()) if m else None


def _num(val):
    if val is None:
        return None
    if isinstance(val, (int, float)):
        return float(val)
    m = re.search(r"[\d.]+", str(val).replace(",", ""))
    return float(m.group()) if m else None


def _deep_find_records(node, needed=("price",)) -> list[dict]:
    """Walk a nested structure and return the largest list of listing-like dicts.

    A listing-like dict has a price plus at least one of bedrooms/area/size. This
    makes us resilient to the exact `__NEXT_DATA__` path changing between deploys.
    """
    best: list[dict] = []

    def _has_fields(d):
        if not isinstance(d, dict):
            return False
        has_price = any(k in d for k in ("price", "priceValue", "price_value"))
        has_attr = any(k in d for k in ("bedrooms", "rooms", "beds", "area", "size", "builtUpArea"))
        return has_price and has_attr

    def looks_like(d):
        # A list element is listing-like if it (or a common wrapper child such as
        # Property Finder's `property`) carries price + an attribute.
        if not isinstance(d, dict):
            return False
        if _has_fields(d):
            return True
        return any(_has_fields(d.get(w)) for w in ("property", "listing", "node"))

    def walk(n):
        nonlocal best
        if isinstance(n, list):
            hits = [x for x in n if looks_like(x)]
            if len(hits) > len(best):
                best = hits
            for x in n:
                walk(x)
        elif isinstance(n, dict):
            for v in n.values():
                walk(v)

    walk(node)
    return best


# ── portal scrapers ──────────────────────────────────────────────────────────
class _PortalScraper(ListingConnector):
    """Base for the three Next.js portals."""

    city_slug: dict[str, str] = {}     # "Dubai" -> url fragment
    area_unit: str = "sqft"            # "sqft" or "sqm" (converted to sqft)

    def __init__(self, cities=("Dubai", "Abu Dhabi"), max_pages=5,
                 browse: BrowseConfig | None = None, debug_dir: str | None = None):
        self.cities = cities
        self.max_pages = max_pages
        self.browse = browse or BrowseConfig()
        self.debug_dir = Path(debug_dir) if debug_dir else None

    # -- to override per site --
    def page_url(self, city: str, page: int) -> str:
        raise NotImplementedError

    def parse_record(self, rec: dict, city: str) -> dict | None:
        raise NotImplementedError

    # -- shared --
    def _extract_next_data(self, page) -> dict | None:
        try:
            raw = page.locator("#__NEXT_DATA__").first.inner_text(timeout=15_000)
            return json.loads(raw)
        except Exception:
            try:
                return page.evaluate("() => window.__NEXT_DATA__")
            except Exception:
                return None

    def fetch(self) -> pd.DataFrame:
        rows: list[dict] = []
        with BrowserSession(self.browse) as sess:
            for city in self.cities:
                for page_no in range(1, self.max_pages + 1):
                    url = self.page_url(city, page_no)
                    if not sess.goto(url):
                        break
                    data = self._extract_next_data(sess.page)
                    if data is None:
                        break
                    if self.debug_dir:
                        self.debug_dir.mkdir(parents=True, exist_ok=True)
                        (self.debug_dir / f"{self.name}_{city}_{page_no}.json").write_text(
                            json.dumps(data)[:5_000_000]
                        )
                    records = self._records(data)
                    if not records:
                        break
                    for rec in records:
                        parsed = self.parse_record(rec, city)
                        if parsed and parsed.get("price"):
                            rows.append(parsed)
        return pd.DataFrame(rows, columns=self.columns) if rows else pd.DataFrame(columns=self.columns)

    def _records(self, data: dict) -> list[dict]:
        return _deep_find_records(data)

    def _location_parts(self, loc) -> tuple[str | None, str | None, str]:
        """From a location hierarchy (list of {name,...}) return (city, area, building)."""
        names = []
        if isinstance(loc, list):
            for item in loc:
                name = item.get("name") if isinstance(item, dict) else None
                if name:
                    names.append(str(name))
        elif isinstance(loc, str):
            names = [p.strip() for p in loc.split(",")]
        city = next((n for n in names if n in ("Dubai", "Abu Dhabi")), None)
        rest = [n for n in names if n != city]
        area = rest[0] if rest else None
        building = rest[-1] if len(rest) > 1 else ""
        return city, area, building

    def _size_to_sqft(self, val) -> float | None:
        n = _num(val)
        if n is None:
            return None
        return round(n * SQM_TO_SQFT, 1) if self.area_unit == "sqm" else round(n, 1)


class PropertyFinderConnector(_PortalScraper):
    name = "property_finder"
    area_unit = "sqft"
    city_slug = {"Dubai": "dubai", "Abu Dhabi": "abu-dhabi"}

    def page_url(self, city, page):
        slug = self.city_slug.get(city, "dubai")
        return (f"https://www.propertyfinder.ae/en/search?c=1&t=1"
                f"&l={slug}&ob=mr&page={page}")

    def parse_record(self, rec, city):
        prop = rec.get("property", rec)
        city_p, area, building = self._location_parts(
            _first(prop, "location.tree", "location.coordinates", "location", default=[])
            or prop.get("location", [])
        )
        url = _first(prop, "share_url", "details_url", "url", "slug")
        if url and not str(url).startswith("http"):
            url = "https://www.propertyfinder.ae" + str(url)
        return {
            "listing_id": f"pf_{_first(prop, 'id', 'reference', default='')}",
            "source": self.name,
            "url": url,
            "city": city_p or city,
            "area": area,
            "building": building,
            "property_type": _canon_type(_first(prop, "property_type", "type", "category.name")),
            "bedrooms": _to_beds(_first(prop, "bedrooms", "rooms")),
            "size_sqft": self._size_to_sqft(_first(prop, "size.value", "size", "area")),
            "price": _num(_first(prop, "price.value", "price", "priceValue")),
            "listed_date": (_first(prop, "listed_date", "created_at")
                            or pd.Timestamp.utcnow().date().isoformat())[:10],
        }


class _EMPGScraper(_PortalScraper):
    """Bayut and Dubizzle share the same (EMPG/Algolia) data shape."""

    area_unit = "sqm"  # Algolia `area` is in sqm; converted to sqft

    def parse_record(self, rec, city):
        city_p, area, building = self._location_parts(rec.get("location", []))
        return {
            "listing_id": f"{self.name}_{_first(rec, 'externalID', 'id', 'objectID', default='')}",
            "source": self.name,
            "url": self._detail_url(rec),
            "city": city_p or city,
            "area": area,
            "building": building or _first(rec, "project.name", default=""),
            "property_type": _canon_type(self._category(rec)),
            "bedrooms": _to_beds(_first(rec, "rooms", "bedrooms", "beds")),
            "size_sqft": self._size_to_sqft(_first(rec, "area", "size", "builtUpArea")),
            "price": _num(_first(rec, "price", "priceValue")),
            "listed_date": self._date(rec),
        }

    def _detail_url(self, rec):
        raise NotImplementedError

    def _category(self, rec):
        # Algolia `category` is a hierarchy list; the last name is the unit type.
        cat = rec.get("category")
        if isinstance(cat, list) and cat:
            last = cat[-1]
            return last.get("name") if isinstance(last, dict) else last
        return _first(rec, "category.name", "type")

    def _date(self, rec):
        ts = _first(rec, "createdAt", "reactivatedAt")
        if isinstance(ts, (int, float)):
            return pd.Timestamp.fromtimestamp(ts, "UTC").date().isoformat()
        return pd.Timestamp.utcnow().date().isoformat()


class BayutConnector(_EMPGScraper):
    name = "bayut"
    city_slug = {"Dubai": "dubai", "Abu Dhabi": "abu-dhabi"}

    def page_url(self, city, page):
        slug = self.city_slug.get(city, "dubai")
        return f"https://www.bayut.com/for-sale/property/{slug}/?page={page}"

    def _detail_url(self, rec):
        slug = _first(rec, "slug", "externalID", default="")
        return f"https://www.bayut.com/property/details-{slug}.html"


class DubizzleConnector(_EMPGScraper):
    name = "dubizzle"
    city_slug = {"Dubai": "dubai", "Abu Dhabi": "abu-dhabi"}

    def page_url(self, city, page):
        slug = self.city_slug.get(city, "dubai")
        return (f"https://uae.dubizzle.com/property-for-sale/residential/"
                f"?cities={slug}&page={page}")

    def _detail_url(self, rec):
        slug = _first(rec, "slug", "externalID", default="")
        return f"https://uae.dubizzle.com/property-for-sale/{slug}/"


class RedditConnector(ListingConnector):
    """Off-market and FSBO leads from local subreddits.

    Reddit's public JSON (append `.json` to any listing) needs no auth or browser.
    Posts are free text, so we extract price/area/beds heuristically and flag
    low-confidence rows — treat these as leads to verify, not clean inventory.
    """

    name = "reddit"

    def __init__(self, subreddits=("dubai", "UAE", "DubaiRealEstate"), limit=100, timeout=15):
        self.subreddits = subreddits
        self.limit = limit
        self.timeout = timeout

    def fetch(self) -> pd.DataFrame:
        rows = []
        headers = {"User-Agent": "propertydeal-finder/1.0"}
        for sub in self.subreddits:
            url = f"https://www.reddit.com/r/{sub}/search.json"
            params = {"q": "for sale apartment OR villa", "restrict_sr": 1,
                      "sort": "new", "limit": self.limit}
            try:
                resp = requests.get(url, params=params, headers=headers, timeout=self.timeout)
                resp.raise_for_status()
                children = resp.json().get("data", {}).get("children", [])
            except Exception:
                continue
            for child in children:
                parsed = self._parse_post(child.get("data", {}))
                if parsed:
                    rows.append(parsed)
        return pd.DataFrame(rows, columns=self.columns) if rows else pd.DataFrame(columns=self.columns)

    _PRICE_RE = re.compile(r"(?:aed|dhs?)\s*([\d,]+(?:\.\d+)?)\s*(k|m|million)?", re.I)
    _SQFT_RE = re.compile(r"([\d,]+)\s*(?:sq\.?\s?ft|sqft|sf)", re.I)
    _BED_RE = re.compile(r"(\d+)\s*(?:br|bed|bedroom)|studio", re.I)

    def _parse_post(self, post: dict) -> dict | None:
        text = f"{post.get('title', '')} {post.get('selftext', '')}"
        price = self._extract_price(text)
        if not price:
            return None
        sqft_m = self._SQFT_RE.search(text)
        return {
            "listing_id": f"reddit_{post.get('id')}",
            "source": "reddit",
            "url": "https://www.reddit.com" + post.get("permalink", ""),
            "city": "Dubai" if "dubai" in text.lower() else pd.NA,
            "area": pd.NA,
            "building": "",
            "property_type": "villa" if "villa" in text.lower() else "apartment",
            "bedrooms": self._extract_beds(text),
            "size_sqft": float(sqft_m.group(1).replace(",", "")) if sqft_m else pd.NA,
            "price": price,
            "listed_date": pd.Timestamp.fromtimestamp(post.get("created_utc", 0), "UTC").date().isoformat(),
        }

    def _extract_price(self, text: str):
        m = self._PRICE_RE.search(text)
        if not m:
            return None
        val = float(m.group(1).replace(",", ""))
        unit = (m.group(2) or "").lower()
        if unit == "k":
            val *= 1_000
        elif unit in ("m", "million"):
            val *= 1_000_000
        return val if val >= 100_000 else None

    def _extract_beds(self, text: str):
        m = self._BED_RE.search(text)
        if not m:
            return pd.NA
        return 0 if m.group(0).lower() == "studio" else int(m.group(1))
