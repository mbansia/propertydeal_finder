# Property Deal Finder

**UAE Real Estate Deal Scraper & Analyzer** for Dubai and Abu Dhabi.

Scrapes residential property listings from **Bayut**, **Dubizzle**, and **Property Finder**, stores them in a local database, analyzes deals using market comparisons and rental yield calculations, then ranks properties with a deal score. Top-scoring deals get deep AI-powered investment analysis via **Ollama** (local LLM, no API keys needed).

## Features

- **Multi-source scraping** — Bayut.com, Dubizzle.com, PropertyFinder.ae
- **All residential types** — Apartments, villas, townhouses, penthouses, duplexes
- **Deal scoring (0-100)** based on:
  - Price vs neighborhood median (40%)
  - Price per sqft vs area median (30%)
  - Estimated rental yield (30%)
- **AI-powered analysis** — Top deals investigated locally via Ollama with investment ratings, risk factors, and rental potential
- **Web dashboard** — Filter, sort, browse deals, view AI analysis
- **Market overview** — AI-generated market summary

## Quick Start (Local Dev)

```bash
# 1. Clone & install
git clone https://github.com/mbansia/propertydeal_finder.git
cd propertydeal_finder
pip install -r requirements.txt

# 2. Configure Ollama (choose one)
# - LOCAL: install Ollama from ollama.com, then: ollama pull llama3.1
# - HOSTED: create .env with OLLAMA_BASE_URL=https://ollama.com and OLLAMA_API_KEY=...

# 3. Run everything (scrape + analyze)
python run_scraper.py run

# 4. Start the dashboard
python run_scraper.py server
# Open http://localhost:8000
```

For deploying this to a hosted URL, see [Deploy from GitHub](#deploy-from-github) below.

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
│   └── ai_analyzer.py      # Ollama LLM integration
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
- **Ollama** — AI analysis (local or via Ollama Cloud API)
- **Vanilla JS** — Dashboard frontend

## Deploy from GitHub

### Option A: Render (Recommended - free tier)

1. Push this repo to GitHub (done)
2. Go to https://render.com and sign in with GitHub
3. Click **New → Blueprint** and select the `propertydeal_finder` repo
4. Render auto-detects `render.yaml` and creates the service
5. In the Render dashboard, set the `OLLAMA_API_KEY` env var (from https://ollama.com/settings/keys)
6. Deploy. Your app will be live at `https://propertydeal-finder.onrender.com`

**For persistent data** (so SQLite survives redeploys): upgrade to the Starter plan ($7/mo) and uncomment the `disk:` block in `render.yaml`. On free tier, data resets on each deploy.

### Option B: Railway

1. Go to https://railway.app and sign in with GitHub
2. **New Project → Deploy from GitHub Repo** → select `propertydeal_finder`
3. Railway detects `Dockerfile` and `railway.json`
4. Add environment variables in Railway dashboard:
   - `OLLAMA_BASE_URL` = `https://ollama.com`
   - `OLLAMA_MODEL` = `gpt-oss:20b`
   - `OLLAMA_API_KEY` = your key
5. Railway provides a persistent volume by default for `/app/data`

### Option C: Fly.io

```bash
fly launch                     # uses the Dockerfile
fly secrets set OLLAMA_API_KEY=your-key OLLAMA_BASE_URL=https://ollama.com
fly volumes create data --size 1
fly deploy
```

### Why not Vercel?

Vercel is serverless (10-60s execution, no persistent disk, no background workers). This app needs long-running scrapes, SQLite persistence, and background tasks — use Render/Railway/Fly instead.

### Required Environment Variables

| Var | Example | Notes |
|-----|---------|-------|
| `OLLAMA_BASE_URL` | `https://ollama.com` | Hosted endpoint |
| `OLLAMA_MODEL` | `gpt-oss:20b` or `llama3.1:70b` | Pick from https://ollama.com/library |
| `OLLAMA_API_KEY` | `ollama-...` | Get at https://ollama.com/settings/keys |
