"""Data connectors.

Two families, both emitting the normalized schemas in `dealfinder.schema`:

  Listing sources (current asking prices):
    bayut, dubizzle, property_finder, reddit

  Transaction sources (recorded sale/rent prices — the comps):
    dld, adre, dxbconnect

Each connector isolates the messy, source-specific bit (HTML scrape, portal CSV,
API JSON) so the engine only ever sees clean rows. Connectors default to
documenting their real endpoint and mapping raw exports; wire credentials/paths
in to pull live data.
"""

from .base import ListingConnector, TransactionConnector

__all__ = ["ListingConnector", "TransactionConnector"]
