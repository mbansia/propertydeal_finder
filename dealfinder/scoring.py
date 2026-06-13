"""Turn listings + benchmarks into ranked deals.

For each listing we answer two questions:
  1. How far below comps is it asking?  (undervaluation)
  2. What net rental yield does it throw off at that price?  (cash return)
Then we blend the two into a single 0–100 deal score, scaled by how much we
trust the underlying comps, and attach human-readable flags for anything that
warrants a second look before you act.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .benchmarks import Benchmark
from .config import Config


def _clamp01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _norm(value: float, floor: float, cap: float) -> float:
    if cap <= floor:
        return 0.0
    return _clamp01((value - floor) / (cap - floor))


def score_listings(
    listings: pd.DataFrame,
    sale_bench: Benchmark,
    rent_bench: Benchmark,
    cfg: Config,
    as_of: pd.Timestamp | None = None,
) -> pd.DataFrame:
    as_of = as_of or pd.Timestamp.today().normalize()
    s, y, b = cfg.score, cfg.yield_, cfg.benchmark
    w_u = s.weights["undervaluation"]
    w_y = s.weights["net_yield"]

    rows = []
    for r in listings.itertuples(index=False):
        size = float(r.size_sqft)
        price = float(r.price)
        if size <= 0 or price <= 0:
            continue

        sale = sale_bench.lookup(r.city, r.area, r.property_type, r.bedrooms)
        rent = rent_bench.lookup(r.city, r.area, r.property_type, r.bedrooms)

        listing_ppsf = price / size
        bench_ppsf = sale.ppsf if sale else np.nan
        fair_value = bench_ppsf * size if sale else np.nan
        discount = (1 - listing_ppsf / bench_ppsf) if sale else np.nan

        # Rental yield, net of service charge, management and vacancy.
        gross_rent = rent.ppsf * size if rent else np.nan
        if rent:
            costs = (
                y.service_charge_per_sqft * size
                + y.mgmt_cost_ratio * gross_rent
                + y.vacancy_ratio * gross_rent
            )
            net_rent = gross_rent - costs
            gross_yield = gross_rent / price
            net_yield = net_rent / price
        else:
            net_rent = gross_yield = net_yield = np.nan

        u_norm = _norm(discount, s.undervaluation_floor, s.undervaluation_cap) if sale else 0.0
        y_norm = _norm(net_yield, s.net_yield_floor, s.net_yield_cap) if rent else 0.0

        quality = w_u * u_norm + w_y * y_norm
        sale_conf = sale.confidence if sale else 0.0
        rent_conf = rent.confidence if rent else 0.0
        confidence = w_u * sale_conf + w_y * rent_conf

        listing_age = (as_of - pd.to_datetime(r.listed_date)).days
        freshness = 1.0 if listing_age <= s.listing_fresh_days else 0.85
        conf_factor = max(s.min_confidence, np.sqrt(confidence) * freshness)
        deal_score = round(100 * quality * conf_factor, 1)

        flags = []
        if sale and discount >= s.suspicious_discount:
            flags.append("suspicious-discount")
        if not sale:
            flags.append("no-sale-comps")
        if not rent:
            flags.append("no-rent-comps")
        if confidence < s.min_confidence:
            flags.append("thin-comps")
        if listing_age > s.listing_fresh_days:
            flags.append("stale-listing")

        rows.append({
            "listing_id": r.listing_id,
            "source": r.source,
            "city": r.city,
            "area": r.area,
            "building": r.building,
            "property_type": r.property_type,
            "bedrooms": r.bedrooms,
            "size_sqft": round(size),
            "price": round(price),
            "listing_ppsf": round(listing_ppsf, 1),
            "benchmark_ppsf": round(bench_ppsf, 1) if sale else np.nan,
            "fair_value": round(fair_value) if sale else np.nan,
            "discount_pct": round(discount * 100, 1) if sale else np.nan,
            "gross_yield_pct": round(gross_yield * 100, 2) if rent else np.nan,
            "net_yield_pct": round(net_yield * 100, 2) if rent else np.nan,
            "est_annual_rent": round(gross_rent) if rent else np.nan,
            "comp_samples": sale.samples if sale else 0,
            "comp_segment": sale.segment if sale else "",
            "confidence": round(confidence, 2),
            "deal_score": deal_score,
            "flags": ";".join(flags),
            "listed_date": r.listed_date,
            "url": r.url,
        })

    deals = pd.DataFrame(rows)
    if deals.empty:
        return deals
    return deals.sort_values("deal_score", ascending=False).reset_index(drop=True)
