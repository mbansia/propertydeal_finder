"""Run the live scrapers and refresh the listings data.

  python -m dealfinder.scrape --sources bayut,property_finder --max-pages 5
  python -m dealfinder.scrape --all --cities Dubai,"Abu Dhabi" --out data/live/listings.csv

Each source runs independently; one failing (anti-bot, layout change, network)
does not abort the others. Rows are de-duplicated on listing_id, so re-running
augments rather than clobbers. Reddit needs no browser; the three portals do
(`playwright install --with-deps chromium`).
"""

from __future__ import annotations

import argparse
import logging
import time

from .config import Config
from .connectors.browser import BrowseConfig
from .connectors.listings import (
    BayutConnector,
    DubizzleConnector,
    PropertyFinderConnector,
    RedditConnector,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("scrape")

SOURCES = {
    "bayut": BayutConnector,
    "dubizzle": DubizzleConnector,
    "property_finder": PropertyFinderConnector,
    "reddit": RedditConnector,
}


def run_scrape(sources, cities, max_pages, out, headful=False, debug_dir=None) -> int:
    browse = BrowseConfig(headless=not headful)
    total = 0
    for name in sources:
        cls = SOURCES.get(name)
        if not cls:
            log.warning("Unknown source: %s", name)
            continue
        log.info("Scraping %s …", name)
        t0 = time.time()
        try:
            if name == "reddit":
                conn = cls()
            else:
                conn = cls(cities=cities, max_pages=max_pages, browse=browse, debug_dir=debug_dir)
            new = conn.append_to(out)
            log.info("  %s: %d listings in %.0fs", name, len(new), time.time() - t0)
            total += len(new)
        except Exception as e:  # keep going on per-source failure
            log.error("  %s failed: %s", name, e)
    log.info("Done. %d listings written to %s", total, out)
    return total


def main(argv=None):
    cfg = Config.load()
    p = argparse.ArgumentParser(prog="dealfinder.scrape", description="Refresh listing data.")
    p.add_argument("--sources", help="comma-separated: bayut,dubizzle,property_finder,reddit")
    p.add_argument("--all", action="store_true", help="scrape every source")
    p.add_argument("--cities", default="Dubai,Abu Dhabi", help="comma-separated cities")
    p.add_argument("--max-pages", type=int, default=5, help="result pages per city")
    p.add_argument("--out", default=cfg.paths["listings"], help="output listings CSV")
    p.add_argument("--headful", action="store_true", help="show the browser (debugging)")
    p.add_argument("--debug-dir", help="dump raw __NEXT_DATA__ here for mapping checks")
    args = p.parse_args(argv)

    sources = list(SOURCES) if args.all else (
        [s.strip() for s in args.sources.split(",")] if args.sources else ["reddit"]
    )
    cities = [c.strip() for c in args.cities.split(",")]
    run_scrape(sources, cities, args.max_pages, args.out, args.headful, args.debug_dir)


if __name__ == "__main__":
    main()
