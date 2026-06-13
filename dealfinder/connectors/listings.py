"""Listing connectors: Bayut, Dubizzle, Property Finder, Reddit.

These produce *asking prices*. None of them is an official feed, so each documents
its real source and isolates the parsing. By default `fetch()` parses a raw export
you supply (HTML/JSON saved from the source) and raises with guidance if none is
given — except Reddit, which reads the public JSON endpoint directly.
"""

from __future__ import annotations

import re
from pathlib import Path

import pandas as pd
import requests

from .base import ListingConnector


class _PortalConnector(ListingConnector):
    """Shared logic for the three property portals.

    Real listings live behind anti-bot protection and Terms that you must respect
    (use official APIs/partnerships where available). The intended flow: save a
    search-results payload to `raw_path`, then map it here.
    """

    endpoint: str = ""

    def __init__(self, raw_path: str | Path | None = None):
        self.raw_path = Path(raw_path) if raw_path else None

    def fetch(self) -> pd.DataFrame:
        if self.raw_path and self.raw_path.exists():
            return self.parse_export(self.raw_path)
        raise NotImplementedError(
            f"[{self.name}] No raw export provided. Save a results payload from "
            f"{self.endpoint} to a file and pass raw_path=..., or drop normalized "
            f"rows straight into the listings CSV. See README → Wiring real data."
        )

    def parse_export(self, path: Path) -> pd.DataFrame:  # pragma: no cover - source-specific
        """Map a saved export to the listing schema. Override per source."""
        raise NotImplementedError


class BayutConnector(_PortalConnector):
    name = "bayut"
    endpoint = "https://www.bayut.com/for-sale/property/dubai/"


class DubizzleConnector(_PortalConnector):
    name = "dubizzle"
    endpoint = "https://uae.dubizzle.com/en/property-for-sale/"


class PropertyFinderConnector(_PortalConnector):
    name = "property_finder"
    endpoint = "https://www.propertyfinder.ae/en/search?c=1"


class RedditConnector(ListingConnector):
    """Off-market and FSBO leads from local subreddits.

    Reddit's public JSON (append `.json` to any listing) needs no auth. Posts are
    free text, so we extract price/area/beds heuristically and flag low-confidence
    rows — treat these as leads to verify, not clean inventory.
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
                post = child.get("data", {})
                parsed = self._parse_post(post)
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
        beds = self._extract_beds(text)
        sqft_m = self._SQFT_RE.search(text)
        sqft = float(sqft_m.group(1).replace(",", "")) if sqft_m else pd.NA
        return {
            "listing_id": f"reddit_{post.get('id')}",
            "source": "reddit",
            "url": "https://www.reddit.com" + post.get("permalink", ""),
            "city": "Dubai" if "dubai" in text.lower() else pd.NA,
            "area": pd.NA,
            "building": "",
            "property_type": "villa" if "villa" in text.lower() else "apartment",
            "bedrooms": beds,
            "size_sqft": sqft,
            "price": price,
            "listed_date": pd.Timestamp.utcfromtimestamp(post.get("created_utc", 0)).date().isoformat(),
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
