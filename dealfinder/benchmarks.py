"""Build per-sqft benchmarks (comps) from recorded transactions.

The benchmark is the heart of the tool. A listing is only a "deal" relative to
what comparable units *actually sold (or rented) for* — not relative to other
asking prices, which can all be inflated together. We therefore price every
listing against recorded DLD/ADRE/DXBconnect transactions.

For each market segment (city → area → type → bedrooms) we compute a
recency-weighted, outlier-trimmed median price-per-sqft. Segments with too few
sales fall back to progressively coarser segments so every listing still gets a
defensible number, with a confidence score that reflects the compromise.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class BenchResult:
    ppsf: float          # recency-weighted median price per sqft for the segment
    samples: int         # number of transactions backing it
    confidence: float    # 0–1, blends sample depth and segment specificity
    level: int           # which fallback level matched (0 = most specific)
    segment: str         # human-readable segment that was used


def _weighted_median(values: np.ndarray, weights: np.ndarray) -> float:
    order = np.argsort(values)
    values, weights = values[order], weights[order]
    cum = np.cumsum(weights)
    cutoff = cum[-1] / 2.0
    return float(values[np.searchsorted(cum, cutoff)])


def _trim(df: pd.DataFrame, col: str, pct: float) -> pd.DataFrame:
    if pct <= 0 or len(df) < 5:
        return df
    lo, hi = df[col].quantile(pct), df[col].quantile(1 - pct)
    return df[(df[col] >= lo) & (df[col] <= hi)]


class Benchmark:
    """A queryable set of per-sqft benchmarks across fallback levels."""

    def __init__(self, levels: list[list[str]], tables: list[dict], min_samples: int):
        self._levels = levels
        self._tables = tables  # parallel to levels: {segment_key_tuple: (ppsf, eff_n, raw_n)}
        self._min_samples = min_samples

    def lookup(self, city, area, property_type, bedrooms) -> BenchResult | None:
        attrs = {
            "city": city,
            "area": area,
            "property_type": property_type,
            "bedrooms": bedrooms,
        }
        for i, keys in enumerate(self._levels):
            key = tuple(attrs[k] for k in keys)
            stat = self._tables[i].get(key)
            if stat is None:
                continue
            ppsf, eff_n, raw_n = stat
            if raw_n < self._min_samples:
                continue
            specificity = max(0.4, 1.0 - 0.12 * i)
            sample_conf = min(1.0, eff_n / (self._min_samples * 2))
            confidence = round(sample_conf * specificity, 3)
            segment = ", ".join(f"{k}={attrs[k]}" for k in keys)
            return BenchResult(round(ppsf, 1), int(raw_n), confidence, i, segment)
        return None


def build_benchmark(
    txns: pd.DataFrame,
    *,
    value_col: str,          # "price" (sale) or "annual_rent" (rent)
    levels: list[list[str]],
    lookback_months: int,
    half_life_months: float,
    min_samples: int,
    trim_pct: float,
    as_of: pd.Timestamp | None = None,
) -> Benchmark:
    df = txns.copy().reset_index(drop=True)
    if df.empty:
        return Benchmark(levels, [{} for _ in levels], min_samples)

    as_of = as_of or pd.Timestamp.today().normalize()
    df["txn_date"] = pd.to_datetime(df["txn_date"])
    df["_age_months"] = (as_of - df["txn_date"]).dt.days / 30.44
    df = df[df["_age_months"] <= lookback_months].copy()

    df["ppsf"] = df[value_col] / df["size_sqft"]
    df = df[(df["ppsf"] > 0) & np.isfinite(df["ppsf"])]
    df["w"] = 0.5 ** (df["_age_months"] / half_life_months)

    tables: list[dict] = []
    for keys in levels:
        table: dict = {}
        for seg_key, group in df.groupby(keys, dropna=False):
            group = _trim(group, "ppsf", trim_pct)
            if group.empty:
                continue
            ppsf = _weighted_median(group["ppsf"].to_numpy(), group["w"].to_numpy())
            table[_as_tuple(seg_key)] = (ppsf, float(group["w"].sum()), len(group))
        tables.append(table)
    return Benchmark(levels, tables, min_samples)


def _as_tuple(key):
    return key if isinstance(key, tuple) else (key,)
