#!/usr/bin/env bash
# Periodic scrape loop for the `scraper` service.
#
# On first boot the data volume is empty, so we seed sample TRANSACTIONS as a
# placeholder benchmark (replace by dropping real DLD/ADRE/DXBconnect exports
# into the volume) and start listings empty so only real scraped rows appear.
set -uo pipefail

: "${DEALFINDER_DATA_DIR:=/app/data/live}"
: "${SCRAPE_SOURCES:=reddit}"
: "${SCRAPE_CITIES:=Dubai,Abu Dhabi}"
: "${SCRAPE_MAX_PAGES:=5}"
: "${SCRAPE_INTERVAL_HOURS:=12}"

mkdir -p "$DEALFINDER_DATA_DIR"

if [ ! -f "$DEALFINDER_DATA_DIR/transactions_sale.csv" ]; then
  echo "[bootstrap] seeding placeholder transaction comps into $DEALFINDER_DATA_DIR"
  python -m scripts.seed_sample_data
  # Keep the seeded transaction comps; start listings from real scrapes only.
  rm -f "$DEALFINDER_DATA_DIR/listings.csv"
fi

while true; do
  echo "[scrape] $(date -u) sources=$SCRAPE_SOURCES pages=$SCRAPE_MAX_PAGES"
  python -m dealfinder.scrape \
    --sources "$SCRAPE_SOURCES" \
    --cities "$SCRAPE_CITIES" \
    --max-pages "$SCRAPE_MAX_PAGES" \
    --out "$DEALFINDER_DATA_DIR/listings.csv"
  echo "[scrape] sleeping ${SCRAPE_INTERVAL_HOURS}h"
  sleep "$(( SCRAPE_INTERVAL_HOURS * 3600 ))"
done
