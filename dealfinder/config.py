"""Load and expose the YAML config as a typed object."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_CONFIG = ROOT / "config.yaml"


@dataclass
class BenchmarkCfg:
    lookback_months: int
    half_life_months: float
    min_samples: int
    trim_pct: float
    segment_levels: list[list[str]]


@dataclass
class YieldCfg:
    lookback_months: int
    min_samples: int
    service_charge_per_sqft: float
    mgmt_cost_ratio: float
    vacancy_ratio: float


@dataclass
class ScoreCfg:
    weights: dict
    undervaluation_floor: float
    undervaluation_cap: float
    net_yield_floor: float
    net_yield_cap: float
    min_confidence: float
    listing_fresh_days: int
    suspicious_discount: float


@dataclass
class Config:
    benchmark: BenchmarkCfg
    yield_: YieldCfg
    score: ScoreCfg
    paths: dict = field(default_factory=dict)

    @classmethod
    def load(cls, path: str | Path = DEFAULT_CONFIG) -> "Config":
        raw = yaml.safe_load(Path(path).read_text())
        return cls(
            benchmark=BenchmarkCfg(**raw["benchmark"]),
            yield_=YieldCfg(**raw["yield"]),
            score=ScoreCfg(**raw["score"]),
            paths={k: str(ROOT / v) for k, v in raw["paths"].items()},
        )
