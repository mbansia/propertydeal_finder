"""Parser tests for the listing scrapers (no network / browser needed).

These pin the mapping from each portal's embedded JSON to our schema, so a
refactor can't silently break extraction. They use representative `__NEXT_DATA__`
fragments, not live pages.
"""

from __future__ import annotations

from dealfinder.connectors.listings import (
    BayutConnector,
    DubizzleConnector,
    PropertyFinderConnector,
    _canon_type,
    _deep_find_records,
    _to_beds,
)

PF_NEXT = {"props": {"pageProps": {"searchResult": {"listings": [
    {"property": {
        "id": 12345, "price": {"value": 1850000}, "bedrooms": "2",
        "size": {"value": 1180}, "property_type": "Apartment",
        "share_url": "/en/plp/buy/apartment-12345.html",
        "location": {"tree": [{"name": "Dubai"}, {"name": "Dubai Marina"}, {"name": "Marina Gate"}]},
        "listed_date": "2026-06-10T00:00:00",
    }},
]}}}}

EMPG_NEXT = {"props": {"pageProps": {"searchResult": {"hits": [
    {"externalID": "9988776", "price": 1200000, "rooms": "Studio", "area": 70.0,
     "slug": "marina-gate-1", "category": [{"name": "Residential"}, {"name": "Apartments"}],
     "location": [{"name": "Dubai"}, {"name": "Dubai Marina"}, {"name": "Marina Gate"}],
     "createdAt": 1749513600},
]}}}}


def test_canon_type():
    assert _canon_type("Apartments") == "apartment"
    assert _canon_type("Villa") == "villa"
    assert _canon_type("Town House") == "townhouse"
    assert _canon_type("Penthouse") == "penthouse"


def test_to_beds_handles_studio():
    assert _to_beds("Studio") == 0
    assert _to_beds("2") == 2
    assert _to_beds("3 Bedrooms") == 3
    assert _to_beds(None) is None


def test_deep_find_sees_through_wrapper():
    assert len(_deep_find_records(PF_NEXT)) == 1   # wrapped in {"property": ...}
    assert len(_deep_find_records(EMPG_NEXT)) == 1


def test_property_finder_parse():
    rec = _deep_find_records(PF_NEXT)[0]
    row = PropertyFinderConnector().parse_record(rec, "Dubai")
    assert row["listing_id"] == "pf_12345"
    assert row["city"] == "Dubai"
    assert row["area"] == "Dubai Marina"
    assert row["building"] == "Marina Gate"
    assert row["property_type"] == "apartment"
    assert row["bedrooms"] == 2
    assert row["size_sqft"] == 1180.0
    assert row["price"] == 1850000.0
    assert row["url"].startswith("https://www.propertyfinder.ae")


def test_bayut_parse_converts_sqm_and_studio():
    rec = _deep_find_records(EMPG_NEXT)[0]
    row = BayutConnector().parse_record(rec, "Dubai")
    assert row["property_type"] == "apartment"
    assert row["bedrooms"] == 0          # "Studio" -> 0
    assert row["size_sqft"] == 753.5     # 70 sqm -> sqft
    assert row["price"] == 1200000.0
    assert row["url"].startswith("https://www.bayut.com")


def test_dubizzle_shares_empg_parser():
    rec = _deep_find_records(EMPG_NEXT)[0]
    row = DubizzleConnector().parse_record(rec, "Dubai")
    assert row["source"] == "dubizzle"
    assert row["size_sqft"] == 753.5
    assert row["url"].startswith("https://uae.dubizzle.com")
