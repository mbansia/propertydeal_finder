"""Orchestrate the full run: load data → build comps → score → rank."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .benchmarks import build_benchmark
from .config import Config
from .scoring import score_listings


def _read(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Missing data file: {path}\n"
            "Run `python -m scripts.seed_sample_data` to generate sample data, "
            "or point config.yaml at your own connector output."
        )
    return pd.read_csv(path)


def find_deals(cfg: Config | None = None, as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Run the end-to-end pipeline and return a ranked deals table."""
    cfg = cfg or Config.load()

    listings = _read(cfg.paths["listings"])
    sales = _read(cfg.paths["transactions_sale"])
    rents = _read(cfg.paths["transactions_rent"])

    sale_bench = build_benchmark(
        sales,
        value_col="price",
        levels=cfg.benchmark.segment_levels,
        lookback_months=cfg.benchmark.lookback_months,
        half_life_months=cfg.benchmark.half_life_months,
        min_samples=cfg.benchmark.min_samples,
        trim_pct=cfg.benchmark.trim_pct,
        as_of=as_of,
    )
    rent_bench = build_benchmark(
        rents,
        value_col="annual_rent",
        levels=cfg.benchmark.segment_levels,
        lookback_months=cfg.yield_.lookback_months,
        half_life_months=cfg.benchmark.half_life_months,
        min_samples=cfg.yield_.min_samples,
        trim_pct=cfg.benchmark.trim_pct,
        as_of=as_of,
    )

    return score_listings(listings, sale_bench, rent_bench, cfg, as_of=as_of)


def run_and_save(cfg: Config | None = None) -> pd.DataFrame:
    cfg = cfg or Config.load()
    deals = find_deals(cfg)
    out = Path(cfg.paths["output"])
    out.parent.mkdir(parents=True, exist_ok=True)
    deals.to_csv(out, index=False)
    return deals
