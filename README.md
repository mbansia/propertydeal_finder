# Property Deal Finder

**UAE Real Estate Deal Scraper & Analyzer** for Dubai and Abu Dhabi.

Scrapes residential property listings from **Bayut**, **Dubizzle**, and **Property Finder**, stores them in a local database, analyzes deals using market comparisons and rental yield calculations, then ranks properties with a deal score. Top-scoring deals get deep AI-powered investment analysis via Claude.

## Features

- **Multi-source scraping** — Bayut.com, Dubizzle.com, PropertyFinder.ae
- **All residential types** — Apartments, villas, townhouses, penthouses, duplexes
- **Deal scoring (0-100)** based on:
  - Price vs neighborhood median (40%)
  - Price per sqft vs area median (30%)
  - Estimated rental yield (30%)
- **AI-powered analysis** — Top deals investigated by Claude with investment ratings, risk factors, and rental potential
- **Web dashboard** — Filter, sort, browse deals, view AI analysis
- **Market overview** — AI-generated market summary

## Quick Start

```bash
# 1. Clone & install
git clone https://github.com/mbansia/propertydeal_finder.git
cd propertydeal_finder
pip install -r requirements.txt

# 2. Configure
cp .env.example .env
# Edit .env with your ANTHROPIC_API_KEY

# 3. Run everything (scrape + analyze)
python run_scraper.py run

# 4. Start the dashboard
python run_scraper.py server
# Open http://localhost:8000
```

## CLI Commands

```bash
# Scrape all sources (10 pages each)
python run_scraper.py scrape

# Scrape specific source with more pages
python run_scraper.py scrape --source bayut --max-pages 20

# Run analysis only (market stats + deal scoring + AI)
python run_scraper.py analyze

# Run analysis without AI (no API key needed)
python run_scraper.py analyze --no-ai

# Start web dashboard
python run_scraper.py server --port 8000
```

## Dashboard API

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/properties` | GET | List/filter properties |
| `/api/properties/{id}` | GET | Property detail |
| `/api/top-deals` | GET | Top-scored deals |
| `/api/stats` | GET | Database statistics |
| `/api/filters` | GET | Available filter values |
| `/api/scrape` | POST | Trigger scrape run |
| `/api/analyze` | POST | Trigger analysis |
| `/api/ai-analyze/{id}` | POST | AI-analyze a property |
| `/api/market-overview` | GET | AI market overview |

## Project Structure

```
propertydeal_finder/
├── main.py                 # FastAPI app & API routes
├── run_scraper.py          # CLI entry point
├── config.py               # Settings & environment config
├── requirements.txt
├── database/
│   ├── db.py               # SQLite connection
│   └── models.py           # Property, MarketStats, AnalysisResult
├── scrapers/
│   ├── base.py             # Base scraper with rate limiting
│   ├── bayut.py            # Bayut.com scraper
│   ├── dubizzle.py         # Dubizzle.com scraper
│   └── propertyfinder.py   # PropertyFinder.ae scraper
├── analysis/
│   ├── metrics.py          # Market stats, deal scoring
│   └── ai_analyzer.py      # Claude API integration
└── dashboard/
    ├── templates/index.html
    └── static/
        ├── style.css
        └── app.js
```

## Tech Stack

- **Python 3.11+** — Backend
- **FastAPI** — Web framework & API
- **SQLite + SQLAlchemy** — Database
- **httpx + BeautifulSoup** — Scraping
- **Claude API (Anthropic)** — AI analysis
- **Vanilla JS** — Dashboard frontend
