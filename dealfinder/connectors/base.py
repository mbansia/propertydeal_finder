"""Base classes for data connectors."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

import pandas as pd

from ..schema import LISTING_COLUMNS, RENT_TXN_COLUMNS, SALE_TXN_COLUMNS


class _BaseConnector(ABC):
    name: str = "base"
    columns: list[str] = []

    @abstractmethod
    def fetch(self) -> pd.DataFrame:
        """Return rows in the connector's normalized schema."""

    def normalize(self, df: pd.DataFrame) -> pd.DataFrame:
        """Coerce to the canonical schema: keep known columns, fill the rest."""
        out = pd.DataFrame()
        for col in self.columns:
            out[col] = df[col] if col in df.columns else pd.NA
        if "source" in out.columns:
            out["source"] = self.name
        return out

    def append_to(self, path: str | Path) -> pd.DataFrame:
        """Fetch and append to a normalized CSV, de-duplicating on id."""
        path = Path(path)
        new = self.normalize(self.fetch())
        id_col = self.columns[0]
        if path.exists():
            combined = pd.concat([pd.read_csv(path), new], ignore_index=True)
            combined = combined.drop_duplicates(subset=[id_col], keep="last")
        else:
            combined = new
        path.parent.mkdir(parents=True, exist_ok=True)
        combined.to_csv(path, index=False)
        return new


class ListingConnector(_BaseConnector):
    """Sources of current for-sale listings (asking prices)."""

    columns = LISTING_COLUMNS


class TransactionConnector(_BaseConnector):
    """Sources of recorded transactions (the comps)."""

    kind = "sale"  # "sale" or "rent"

    @property
    def columns(self) -> list[str]:  # type: ignore[override]
        return SALE_TXN_COLUMNS if self.kind == "sale" else RENT_TXN_COLUMNS
