"""Tests for the benchmark + scoring engine."""

from __future__ import annotations

import pandas as pd
import pytest

from dealfinder.benchmarks import build_benchmark
from dealfinder.config import Config
from dealfinder.pipeline import find_deals
from dealfinder.scoring import score_listings

AS_OF = pd.Timestamp("2026-06-13")
LEVELS = [
    ["city", "area", "property_type", "bedrooms"],
    ["city", "area", "property_type"],
    ["city", "property_type"],
]


def _sales(ppsf, n, area="Marina", city="Dubai", ptype="apartment", beds=1, size=800):
    return pd.DataFrame([{
        "txn_id": f"s{i}", "source": "dld", "city": city, "area": area,
        "building": "X", "property_type": ptype, "bedrooms": beds,
        "size_sqft": size, "price": ppsf * size,
        "txn_date": (AS_OF - pd.Timedelta(days=30)).date().isoformat(),
    } for i in range(n)])


def _bench(df):
    return build_benchmark(
        df, value_col="price", levels=LEVELS, lookback_months=12,
        half_life_months=6, min_samples=5, trim_pct=0.1, as_of=AS_OF,
    )


def test_benchmark_returns_median_ppsf():
    b = _bench(_sales(1000, 10))
    res = b.lookup("Dubai", "Marina", "apartment", 1)
    assert res is not None
    assert res.ppsf == pytest.approx(1000, rel=0.01)
    assert res.level == 0
    assert res.samples == 10


def test_benchmark_falls_back_when_thin():
    # Only 2 sales at the finest segment -> must fall back to a coarser level.
    thin = _sales(1200, 2, beds=3)
    broad = _sales(1000, 8, beds=1)
    b = _bench(pd.concat([thin, broad]))
    res = b.lookup("Dubai", "Marina", "apartment", 3)  # finest has only 2
    assert res is not None
    assert res.level > 0  # fell back


def test_benchmark_missing_segment_returns_none():
    b = _bench(_sales(1000, 10))
    assert b.lookup("Abu Dhabi", "Nowhere", "villa", 9) is None


def test_outliers_are_trimmed():
    df = _sales(1000, 20)
    df.loc[0, "price"] = 1000 * 800 * 50  # absurd outlier
    res = _bench(df).lookup("Dubai", "Marina", "apartment", 1)
    assert res.ppsf == pytest.approx(1000, rel=0.05)


def test_scoring_discount_and_yield():
    cfg = Config.load()
    sales = _sales(1000, 10)              # comp = 1000/sqft
    rents = _sales(80, 10).rename(columns={"price": "annual_rent"})
    rents["annual_rent"] = 80 * 800       # 80/sqft rent
    sale_b = _bench(sales)
    rent_b = build_benchmark(
        rents, value_col="annual_rent", levels=LEVELS, lookback_months=12,
        half_life_months=6, min_samples=5, trim_pct=0.1, as_of=AS_OF,
    )
    # Listing asking 850/sqft -> 15% below the 1000 comp.
    listing = pd.DataFrame([{
        "listing_id": "L1", "source": "bayut", "url": "u", "city": "Dubai",
        "area": "Marina", "building": "X", "property_type": "apartment",
        "bedrooms": 1, "size_sqft": 800, "price": 850 * 800,
        "listed_date": AS_OF.date().isoformat(),
    }])
    out = score_listings(listing, sale_b, rent_b, cfg, as_of=AS_OF)
    row = out.iloc[0]
    assert row["discount_pct"] == pytest.approx(15.0, abs=0.5)
    assert row["benchmark_ppsf"] == pytest.approx(1000, rel=0.01)
    assert row["net_yield_pct"] > 0
    assert row["deal_score"] > 0


def test_suspicious_discount_flagged():
    cfg = Config.load()
    sale_b = _bench(_sales(1000, 10))
    rent_b = _bench(_sales(1000, 10))  # reuse; yield irrelevant here
    listing = pd.DataFrame([{
        "listing_id": "L2", "source": "reddit", "url": "u", "city": "Dubai",
        "area": "Marina", "building": "X", "property_type": "apartment",
        "bedrooms": 1, "size_sqft": 800, "price": 400 * 800,  # 60% below comp
        "listed_date": AS_OF.date().isoformat(),
    }])
    out = score_listings(listing, sale_b, rent_b, cfg, as_of=AS_OF)
    assert "suspicious-discount" in out.iloc[0]["flags"]


def test_full_pipeline_on_sample_data():
    deals = find_deals(Config.load())
    assert not deals.empty
    assert deals["deal_score"].is_monotonic_decreasing  # ranked best-first
    assert {"discount_pct", "net_yield_pct", "confidence"}.issubset(deals.columns)
