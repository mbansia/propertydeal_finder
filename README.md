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

# 1. Generate sample data (stands in for live connectors)
python -m scripts.seed_sample_data

# 2. Scan the best deals in the terminal
python -m dealfinder.cli deals --limit 20

# 3. Or open the interactive dashboard
streamlit run app.py
```

The sample dataset includes a handful of genuinely under-priced listings, so the
top of the table shows real-looking deals (15–21% below comps with healthy
yields) the moment you run it.

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

## Wiring real data

The engine reads three normalized CSVs (paths in `config.yaml`). Connectors in
[`dealfinder/connectors/`](dealfinder/connectors/) turn each real source into
those rows:

- **Listings** (asking prices): `bayut`, `dubizzle`, `property_finder`, `reddit`.
  The Reddit connector already pulls public JSON; the three portals are behind
  anti-bot protection and Terms — use their official APIs/partner feeds, save a
  results payload, and map it in the connector's `parse_export`.
- **Transactions** (the comps): `dld`, `adre`, `dxbconnect`. These map cleanly
  from the structured government/portal **CSV exports** — download a file and
  point the connector at it:

```python
from dealfinder.connectors.transactions import DLDConnector
DLDConnector("downloads/dld_transactions.csv", kind="sale").append_to(
    "data/sample/transactions_sale.csv"
)
```

Each connector emits the schema in [`dealfinder/schema.py`](dealfinder/schema.py),
so the engine never cares where a row came from. Swap the sample CSVs for
connector output and everything downstream — scoring, CLI, dashboard — just works.

> **Note on data:** respect each source's Terms of Service and rate limits, and
> treat transaction data per its licence. The bundled data is synthetic and for
> demonstration only — not investment advice. Always verify title, service
> charges, and any flags before acting on a deal.

## Project layout

```
config.yaml                 # all scoring knobs (weights, thresholds, costs)
dealfinder/
  schema.py                 # normalized listing / transaction columns
  benchmarks.py             # recency-weighted, trimmed per-sqft comps + fallback
  scoring.py                # discount + net yield -> 0–100 deal score
  pipeline.py               # load -> benchmark -> score -> rank
  cli.py                    # terminal deal scanner
  connectors/
    listings.py             # Bayut, Dubizzle, Property Finder, Reddit
    transactions.py         # DLD, ADRE, DXBconnect
scripts/seed_sample_data.py # realistic synthetic data generator
app.py                      # Streamlit dashboard
tests/test_engine.py        # benchmark + scoring tests
```

## Tests

```bash
python -m pytest tests/ -q
```
