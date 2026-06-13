"""Generate realistic sample data so the engine runs end-to-end offline.

This stands in for the connectors until you wire real exports. It produces:
  - recorded sale transactions   (the comps)
  - recorded rental contracts     (for yield)
  - current for-sale listings     (what we score)

A handful of listings are deliberately priced below comps so you can see the
engine surface them. Numbers are representative of Dubai/Abu Dhabi market levels
circa 2025–26 but are synthetic — replace with real connector output for live use.

Run:  python -m scripts.seed_sample_data
"""

from __future__ import annotations

import os
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

RNG = np.random.default_rng(42)
ROOT = Path(__file__).resolve().parent.parent
# Honor DEALFINDER_DATA_DIR so deployments can seed straight into their volume.
OUT = Path(os.environ.get("DEALFINDER_DATA_DIR", ROOT / "data" / "sample"))
TODAY = date(2026, 6, 13)

# area -> (city, base sale AED/sqft, gross yield, property_type)
MARKET = {
    "Dubai Marina":      ("Dubai", 1650, 0.066, "apartment"),
    "Jumeirah Village Circle": ("Dubai", 1050, 0.082, "apartment"),
    "Business Bay":      ("Dubai", 1750, 0.068, "apartment"),
    "Downtown Dubai":    ("Dubai", 2250, 0.055, "apartment"),
    "Palm Jumeirah":     ("Dubai", 2500, 0.058, "apartment"),
    "Dubai Hills Estate":("Dubai", 1550, 0.062, "townhouse"),
    "Arabian Ranches":   ("Dubai", 1400, 0.060, "villa"),
    "Al Reem Island":    ("Abu Dhabi", 1200, 0.075, "apartment"),
    "Yas Island":        ("Abu Dhabi", 1450, 0.070, "apartment"),
    "Saadiyat Island":   ("Abu Dhabi", 1950, 0.060, "apartment"),
    "Al Raha Beach":     ("Abu Dhabi", 1350, 0.072, "apartment"),
}

# property_type -> {bedrooms: typical sqft}
SIZES = {
    "apartment": {0: 460, 1: 780, 2: 1180, 3: 1700},
    "townhouse": {3: 2200, 4: 2700},
    "villa": {3: 2900, 4: 3600, 5: 4500},
    "penthouse": {3: 3500, 4: 4800},
}

BUILDINGS = {
    "Dubai Marina": ["Marina Gate", "Princess Tower", "Cayan Tower"],
    "Jumeirah Village Circle": ["Bloom Towers", "Belgravia", "Pantheon"],
    "Business Bay": ["Executive Towers", "Merano", "Damac Maison"],
    "Downtown Dubai": ["Burj Vista", "The Address", "Boulevard Point"],
    "Palm Jumeirah": ["Shoreline", "Azure Residences", "Palme Couture"],
    "Dubai Hills Estate": ["Sidra", "Maple", "Club Villas"],
    "Arabian Ranches": ["Palmera", "Alvorada", "Saheel"],
    "Al Reem Island": ["Sun Tower", "Sky Tower", "Marina Heights"],
    "Yas Island": ["Ansam", "Mayan", "Water's Edge"],
    "Saadiyat Island": ["Mamsha", "Soho Square", "Park View"],
    "Al Raha Beach": ["Al Muneera", "Al Zeina", "Al Bandar"],
}


def _rand_date(within_months: int) -> str:
    days = RNG.integers(0, int(within_months * 30.44))
    return (TODAY - timedelta(days=int(days))).isoformat()


def _beds_for(ptype: str) -> int:
    return int(RNG.choice(list(SIZES[ptype].keys())))


def _size(ptype: str, beds: int) -> float:
    base = SIZES[ptype][beds]
    return round(base * RNG.normal(1.0, 0.06), 1)


def gen_sale_transactions(per_segment=14) -> pd.DataFrame:
    rows = []
    tid = 0
    for area, (city, base_ppsf, _yield, ptype) in MARKET.items():
        for beds in SIZES[ptype]:
            for _ in range(per_segment):
                size = _size(ptype, beds)
                ppsf = base_ppsf * RNG.normal(1.0, 0.07)
                rows.append({
                    "txn_id": f"sale_{tid:05d}",
                    "source": RNG.choice(["dld", "adre", "dxbconnect"]),
                    "city": city,
                    "area": area,
                    "building": RNG.choice(BUILDINGS[area]),
                    "property_type": ptype,
                    "bedrooms": beds,
                    "size_sqft": size,
                    "price": round(ppsf * size, -3),
                    "txn_date": _rand_date(12),
                })
                tid += 1
    return pd.DataFrame(rows)


def gen_rent_transactions(per_segment=12) -> pd.DataFrame:
    rows = []
    tid = 0
    for area, (city, base_ppsf, gyield, ptype) in MARKET.items():
        rent_ppsf = base_ppsf * gyield
        for beds in SIZES[ptype]:
            for _ in range(per_segment):
                size = _size(ptype, beds)
                rppsf = rent_ppsf * RNG.normal(1.0, 0.07)
                rows.append({
                    "txn_id": f"rent_{tid:05d}",
                    "source": "dld",
                    "city": city,
                    "area": area,
                    "building": RNG.choice(BUILDINGS[area]),
                    "property_type": ptype,
                    "bedrooms": beds,
                    "size_sqft": size,
                    "annual_rent": round(rppsf * size, -2),
                    "txn_date": _rand_date(12),
                })
                tid += 1
    return pd.DataFrame(rows)


def gen_listings(n_market=120, n_deals=14) -> pd.DataFrame:
    sources = ["bayut", "dubizzle", "property_finder", "reddit"]
    rows = []
    areas = list(MARKET.keys())

    # Ordinary listings: priced around or slightly above comps.
    for i in range(n_market):
        area = RNG.choice(areas)
        city, base_ppsf, _y, ptype = MARKET[area]
        beds = _beds_for(ptype)
        size = _size(ptype, beds)
        ppsf = base_ppsf * RNG.normal(1.04, 0.06)  # asking skews a touch high
        rows.append(_listing_row(i, RNG.choice(sources), city, area, ptype, beds, size, ppsf, fresh=True))

    # Planted deals: genuinely below comps, fresh listings.
    for j in range(n_deals):
        area = RNG.choice(areas)
        city, base_ppsf, _y, ptype = MARKET[area]
        beds = _beds_for(ptype)
        size = _size(ptype, beds)
        discount = RNG.uniform(0.12, 0.22)
        ppsf = base_ppsf * (1 - discount)
        rows.append(_listing_row(1000 + j, RNG.choice(sources), city, area, ptype, beds, size, ppsf, fresh=True))

    return pd.DataFrame(rows)


def _listing_row(idx, source, city, area, ptype, beds, size, ppsf, fresh=True):
    age = RNG.integers(0, 10) if fresh else RNG.integers(20, 80)
    return {
        "listing_id": f"{source}_{idx:05d}",
        "source": source,
        "url": f"https://example.com/{source}/{idx}",
        "city": city,
        "area": area,
        "building": RNG.choice(BUILDINGS[area]),
        "property_type": ptype,
        "bedrooms": beds,
        "size_sqft": size,
        "price": round(ppsf * size, -3),
        "listed_date": (TODAY - timedelta(days=int(age))).isoformat(),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    gen_sale_transactions().to_csv(OUT / "transactions_sale.csv", index=False)
    gen_rent_transactions().to_csv(OUT / "transactions_rent.csv", index=False)
    gen_listings().to_csv(OUT / "listings.csv", index=False)
    print(f"Wrote sample data to {OUT}/")


if __name__ == "__main__":
    main()
