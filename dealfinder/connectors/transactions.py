"""Transaction connectors: DLD, ADRE, DXBconnect.

These are the comps — actual registered prices. They map cleanly because they
come from structured government / portal exports rather than scraped HTML.

  DLD          Dubai Land Department open data (Dubai Pulse). Sale + rental
               (Ejari) registrations published as CSV.
  ADRE         Abu Dhabi Real Estate (Department of Municipalities & Transport)
               transaction disclosures for Abu Dhabi.
  DXBconnect   Aggregated DLD transaction feed (convenience source for Dubai).

Point each connector at a downloaded export and it maps the source's column
names to our schema.
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from .base import TransactionConnector


class _ExportConnector(TransactionConnector):
    """Maps a downloaded CSV/Excel export to the transaction schema."""

    column_map: dict[str, str] = {}   # source column -> our column
    download_url: str = ""

    def __init__(self, export_path: str | Path | None = None, kind: str = "sale"):
        self.export_path = Path(export_path) if export_path else None
        self.kind = kind

    def fetch(self) -> pd.DataFrame:
        if not self.export_path or not self.export_path.exists():
            raise NotImplementedError(
                f"[{self.name}] No export found. Download a transactions file from "
                f"{self.download_url} and pass export_path=..."
            )
        raw = (
            pd.read_excel(self.export_path)
            if self.export_path.suffix in {".xlsx", ".xls"}
            else pd.read_csv(self.export_path)
        )
        df = raw.rename(columns=self.column_map)
        df["source"] = self.name
        return df


class DLDConnector(_ExportConnector):
    name = "dld"
    download_url = "https://www.dubaipulse.gov.ae/data/dld-transactions"
    # Maps Dubai Pulse transaction columns to our schema.
    column_map = {
        "transaction_id": "txn_id",
        "area_name_en": "area",
        "property_type_en": "property_type",
        "rooms_en": "bedrooms",
        "building_name_en": "building",
        "procedure_area": "size_sqft",   # sqm in source; convert downstream if needed
        "actual_worth": "price",
        "annual_amount": "annual_rent",
        "instance_date": "txn_date",
    }


class ADREConnector(_ExportConnector):
    name = "adre"
    download_url = "https://www.dmt.gov.ae/en/Real-Estate/Transactions"
    column_map = {
        "TransactionNumber": "txn_id",
        "District": "area",
        "UnitType": "property_type",
        "Bedrooms": "bedrooms",
        "Project": "building",
        "AreaSqft": "size_sqft",
        "Value": "price",
        "AnnualRent": "annual_rent",
        "TransactionDate": "txn_date",
    }


class DXBConnectConnector(_ExportConnector):
    name = "dxbconnect"
    download_url = "https://dxbconnect.com/transactions"
    column_map = {
        "id": "txn_id",
        "community": "area",
        "type": "property_type",
        "beds": "bedrooms",
        "tower": "building",
        "size_sqft": "size_sqft",
        "amount": "price",
        "rent_pa": "annual_rent",
        "date": "txn_date",
    }
