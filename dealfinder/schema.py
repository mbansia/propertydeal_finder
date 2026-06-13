"""Normalized data schemas shared across connectors and the engine.

Every connector — whether it scrapes Bayut or parses a DLD CSV export — must
emit rows with these columns. Keeping one schema means the engine never cares
where the data came from.
"""

from __future__ import annotations

# A residential unit currently for sale.
LISTING_COLUMNS = [
    "listing_id",      # stable id from the source
    "source",          # bayut | dubizzle | property_finder | reddit
    "url",             # link so you can act fast
    "city",            # Dubai | Abu Dhabi
    "area",            # community / district, e.g. "Dubai Marina"
    "building",        # tower / project name (optional, "" if unknown)
    "property_type",   # apartment | villa | townhouse | penthouse
    "bedrooms",        # int; 0 = studio
    "size_sqft",       # float, built-up area
    "price",           # AED asking price
    "listed_date",     # ISO date the listing appeared / was last seen
]

# A recorded sale (DLD / ADRE / DXBconnect). This is the source of truth for comps.
SALE_TXN_COLUMNS = [
    "txn_id",
    "source",          # dld | adre | dxbconnect
    "city",
    "area",
    "building",
    "property_type",
    "bedrooms",
    "size_sqft",
    "price",           # AED actual recorded sale price
    "txn_date",        # ISO date of registration
]

# A recorded rental contract (DLD rental index / Ejari via the same portals).
RENT_TXN_COLUMNS = [
    "txn_id",
    "source",
    "city",
    "area",
    "building",
    "property_type",
    "bedrooms",
    "size_sqft",
    "annual_rent",     # AED per year
    "txn_date",
]

CITIES = ["Dubai", "Abu Dhabi"]
PROPERTY_TYPES = ["apartment", "villa", "townhouse", "penthouse"]
