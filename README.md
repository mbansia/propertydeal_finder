# UAE Property Deal Finder

Find under-priced residential listings in **Dubai** and **Abu Dhabi**, fast.

The core idea: a listing is only a *deal* relative to what comparable units have
**actually sold and rented for** — not relative to other asking prices, which can
all be inflated together. So every listing is priced against **recorded
transactions** (DLD · ADRE · DXBconnect), then ranked on two things you care
about when you need to move quickly:

1. **Undervaluation** — how far below comps (per-sqft benchmark) it's asking.
2. **Net rental yield** — the cash return at that price, after costs.

```
 Transactions ──► Benchmarks ──┐
 (DLD/ADRE/DXB)   per-sqft comps │
                                 ├─► Score & rank ─► Top deals (CLI / dashboard / CSV)
 Listings ───────────────────────┘
 (Bayut/Dubizzle/PropertyFinder/Reddit)
```

## Quick start

```bash
pip install -r requirements.txt

# 1. Generate sample data so everything runs offline (stands in for live data)
python -m scripts.seed_sample_data

# 2. Scan the best deals in the terminal
python -m dealfinder.cli deals --limit 20

# 3. Or open the interactive dashboard
streamlit run app.py
```

The sample dataset includes a handful of genuinely under-priced listings, so the
top of the table shows real-looking deals (15–21% below comps with healthy
yields) the moment you run it. To pull **real** listings instead, see
[Live data](#live-data) (browser scraping) and [Deploy](#deploy-on-vultr--coolify).

## How a deal is scored

For each listing the engine:

1. **Finds comps.** Recorded sales are bucketed by `city → area → type → bedrooms`.
   For each bucket it takes a **recency-weighted, outlier-trimmed median
   price-per-sqft**. Thin buckets fall back to coarser ones, and the result
   carries a **confidence** reflecting how many recent sales backed it.
2. **Measures undervaluation.** `discount = 1 − (asking ppsf ÷ comp ppsf)`.
3. **Estimates net yield.** A rent benchmark (built the same way from rental
   contracts) gives expected rent; subtract service charge, management and
   vacancy to get **net yield = net rent ÷ price**.
4. **Scores 0–100.** `55% undervaluation + 45% net yield`, scaled by comp
   confidence and listing freshness. Deals deeper than 40% off are **flagged**
   as too-good-to-be-true (bad data, leasehold, or distressed) rather than
   celebrated.

Everything above — weights, thresholds, cost assumptions, segment levels — is
tunable in [`config.yaml`](config.yaml).

## CLI

```bash
python -m dealfinder.cli deals --city Dubai --min-score 40
python -m dealfinder.cli deals --max-price 1500000 --min-yield 6 --type apartment
python -m dealfinder.cli deals --min-discount 12 --save out/shortlist.csv
python -m dealfinder.cli deals --include-suspicious      # show flagged ultra-discounts
```

| Flag | Meaning |
|------|---------|
| `--city` | `Dubai` / `Abu Dhabi` |
| `--type` | `apartment` / `villa` / `townhouse` / `penthouse` |
| `--source` | `bayut` / `dubizzle` / `property_finder` / `reddit` |
| `--max-price` | cap asking price (AED) |
| `--min-score` / `--min-yield` / `--min-discount` | thresholds |
| `--save PATH` | write the filtered shortlist to CSV |

## Live data

The engine reads three normalized CSVs (paths in `config.yaml`). Connectors in
[`dealfinder/connectors/`](dealfinder/connectors/) produce them.

### Listings — scraped with a headless browser

Bayut, Dubizzle and Property Finder block plain HTTP clients (`requests`/`curl`
get a `403`), so the connectors drive a **headless Chromium via Playwright**
(see [`connectors/browser.py`](dealfinder/connectors/browser.py)) with light
stealth and polite rate-limiting. All three are Next.js apps that embed their
search results as JSON in a `__NEXT_DATA__` tag — we parse that, which is far
more stable than CSS selectors. Reddit needs no browser (public JSON).

```bash
# one-time: install the browser
playwright install --with-deps chromium

# refresh listings (writes to the configured listings CSV, de-duped on id)
python -m dealfinder.scrape --all --max-pages 8
python -m dealfinder.scrape --sources bayut,property_finder --cities Dubai
python -m dealfinder.scrape --sources property_finder --debug-dir out/raw   # dump __NEXT_DATA__
```

If a portal redeploys and the mapping drifts, run with `--debug-dir` to dump the
raw `__NEXT_DATA__` and adjust the field paths in `parse_record`. The parser is
defensive (tries several keys, skips rows it can't read) so a partial change
degrades gracefully instead of crashing.

### Transactions (comps) — DLD / ADRE / DXBconnect exports

Transaction data is published as **bulk files**, so there's nothing to scrape —
download and map:

- **DLD** — Dubai Land Department open data on [Dubai Pulse](https://www.dubaipulse.gov.ae/data/dld-transactions)
  (sale + Ejari rental CSVs, no login).
- **ADRE** — Abu Dhabi transaction disclosures (DMT).
- **DXBconnect** — aggregated DLD feed for convenience.

```python
from dealfinder.connectors.transactions import DLDConnector
DLDConnector("downloads/dld_transactions.csv", kind="sale").append_to(
    "data/live/transactions_sale.csv"
)
```

> **Area-name harmonisation:** DLD sometimes uses different community names than
> the portals (e.g. DLD's *Marsa Dubai* = *Dubai Marina*). Where names don't line
> up, the benchmark automatically falls back to city-level comps, but for
> sharpest per-area pricing add a name-mapping when you load transactions.

Every connector emits the schema in [`dealfinder/schema.py`](dealfinder/schema.py),
so the engine never cares where a row came from.

> **Sandbox note:** these scrapers were built and unit-tested against
> representative payloads but not run against the live sites from the dev
> sandbox, whose network egress allowlist blocks the portals. They run normally
> on a server with open egress (your Vultr box).

> **Note on data:** respect each source's Terms of Service, robots and rate
> limits, and treat transaction data per its licence. Bundled sample data is
> synthetic — not investment advice. Verify title, service charges and any flags
> before acting.

## Deploy on Vultr + Coolify

This app needs a persistent disk, a real browser and long-running processes, so
a small VPS fits and **serverless (Vercel) does not** — no persistent storage,
function timeouts too short for a multi-page scrape, and no Chromium/Streamlit
server. Use a VPS:

1. Create a Vultr instance (2 vCPU / 2–4 GB is plenty) and install Coolify.
2. In Coolify: **New Resource → Docker Compose**, point it at this repo. It reads
   [`docker-compose.yml`](docker-compose.yml), which builds two services off the
   one [`Dockerfile`](Dockerfile):
   - `dashboard` — the Streamlit UI on port `8501` (map your domain to it).
   - `scraper` — [`deploy/scrape-loop.sh`](deploy/scrape-loop.sh): seeds
     placeholder comps on first boot, then re-scrapes every `SCRAPE_INTERVAL_HOURS`.
   Both share a persistent `dealdata` volume (`DEALFINDER_DATA_DIR=/app/data/live`).
3. Drop your DLD/ADRE/DXBconnect transaction CSVs into the volume (or map the
   connectors into the loop) to replace the placeholder comps with real ones.

Tune scraping via env vars: `SCRAPE_SOURCES`, `SCRAPE_CITIES`, `SCRAPE_MAX_PAGES`,
`SCRAPE_INTERVAL_HOURS`. Set `DEALFINDER_DATA_DIR` to relocate the data dir.

## Project layout

```
config.yaml                 # all scoring knobs (weights, thresholds, costs)
dealfinder/
  schema.py                 # normalized listing / transaction columns
  benchmarks.py             # recency-weighted, trimmed per-sqft comps + fallback
  scoring.py                # discount + net yield -> 0–100 deal score
  pipeline.py               # load -> benchmark -> score -> rank
  cli.py                    # terminal deal scanner
  scrape.py                 # run live scrapers, refresh listings
  connectors/
    browser.py              # stealth headless-Chromium (Playwright) session
    listings.py             # Bayut, Dubizzle, Property Finder, Reddit (browser/JSON)
    transactions.py         # DLD, ADRE, DXBconnect (bulk CSV exports)
scripts/seed_sample_data.py # realistic synthetic data generator
app.py                      # Streamlit dashboard
Dockerfile                  # Playwright + Streamlit image
docker-compose.yml          # dashboard + scheduled scraper, for Coolify
deploy/scrape-loop.sh       # periodic scrape + first-boot bootstrap
tests/                      # engine + scraper-parser tests
```

## Tests

```bash
python -m pytest tests/ -q
```
