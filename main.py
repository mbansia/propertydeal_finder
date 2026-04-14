"""Property Deal Finder - FastAPI backend."""

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI, Depends, Query, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, desc
from sqlalchemy.orm import Session

from config import settings
from database.db import get_db, engine
from database.models import Base, Property, MarketStats
from analysis.metrics import AnalysisEngine
from analysis.ai_analyzer import AIAnalyzer
from scrapers.bayut import BayutScraper
from scrapers.dubizzle import DubizzleScraper
from scrapers.propertyfinder import PropertyFinderScraper

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")
    yield


app = FastAPI(
    title="Property Deal Finder",
    description="UAE Property Deal Scraper & Analyzer - Dubai & Abu Dhabi",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/static", StaticFiles(directory="dashboard/static"), name="static")
templates = Jinja2Templates(directory="dashboard/templates")


# --------------- Pages ---------------

@app.get("/")
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})


# --------------- API: Listings ---------------

@app.get("/api/properties")
def list_properties(
    city: str | None = None,
    neighborhood: str | None = None,
    property_type: str | None = None,
    bedrooms: int | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    min_score: float | None = None,
    source: str | None = None,
    sort_by: str = "deal_score",
    sort_dir: str = "desc",
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=200),
    db: Session = Depends(get_db),
):
    query = db.query(Property).filter(Property.is_active == True)

    if city:
        query = query.filter(Property.city == city)
    if neighborhood:
        query = query.filter(Property.neighborhood.ilike(f"%{neighborhood}%"))
    if property_type:
        query = query.filter(Property.property_type.ilike(f"%{property_type}%"))
    if bedrooms is not None:
        query = query.filter(Property.bedrooms == bedrooms)
    if min_price is not None:
        query = query.filter(Property.price >= min_price)
    if max_price is not None:
        query = query.filter(Property.price <= max_price)
    if min_score is not None:
        query = query.filter(Property.deal_score >= min_score)
    if source:
        query = query.filter(Property.source == source)

    # Sorting
    sort_col = getattr(Property, sort_by, Property.deal_score)
    if sort_dir == "asc":
        query = query.order_by(sort_col.asc().nullslast())
    else:
        query = query.order_by(sort_col.desc().nullsfirst())

    total = query.count()
    properties = query.offset((page - 1) * per_page).limit(per_page).all()

    return {
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": (total + per_page - 1) // per_page,
        "properties": [p.to_dict() for p in properties],
    }


@app.get("/api/properties/{property_id}")
def get_property(property_id: int, db: Session = Depends(get_db)):
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        return JSONResponse(status_code=404, content={"error": "Property not found"})
    return prop.to_dict()


# --------------- API: Filters ---------------

@app.get("/api/filters")
def get_filters(db: Session = Depends(get_db)):
    """Get available filter values."""
    cities = [
        r[0] for r in db.query(Property.city).filter(Property.is_active == True).distinct().all()
        if r[0]
    ]
    neighborhoods = [
        r[0]
        for r in db.query(Property.neighborhood)
        .filter(Property.is_active == True)
        .distinct()
        .order_by(Property.neighborhood)
        .all()
        if r[0]
    ]
    sources = [
        r[0] for r in db.query(Property.source).distinct().all()
        if r[0]
    ]
    property_types = [
        r[0]
        for r in db.query(Property.property_type)
        .filter(Property.is_active == True)
        .distinct()
        .all()
        if r[0]
    ]
    bedroom_counts = sorted([
        r[0]
        for r in db.query(Property.bedrooms)
        .filter(Property.is_active == True, Property.bedrooms.isnot(None))
        .distinct()
        .all()
    ])

    return {
        "cities": cities,
        "neighborhoods": neighborhoods,
        "sources": sources,
        "property_types": property_types,
        "bedroom_counts": bedroom_counts,
    }


# --------------- API: Stats ---------------

@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db)):
    engine = AnalysisEngine(db)
    return engine.get_summary_stats()


@app.get("/api/stats/neighborhoods")
def neighborhood_stats(
    city: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(MarketStats)
    if city:
        query = query.filter(MarketStats.city == city)
    stats = query.order_by(MarketStats.neighborhood).all()

    return [
        {
            "city": s.city,
            "neighborhood": s.neighborhood,
            "property_type": s.property_type,
            "bedrooms": s.bedrooms,
            "median_price": s.median_price,
            "median_price_per_sqft": s.median_price_per_sqft,
            "avg_price": s.avg_price,
            "listing_count": s.listing_count,
        }
        for s in stats
    ]


# --------------- API: Top Deals ---------------

@app.get("/api/top-deals")
def top_deals(
    limit: int = Query(20, ge=1, le=100),
    city: str | None = None,
    db: Session = Depends(get_db),
):
    engine = AnalysisEngine(db)
    deals = engine.get_top_deals(limit=limit, city=city)
    return [p.to_dict() for p in deals]


# --------------- API: Actions ---------------

async def _run_scraper(scraper_name: str | None, max_pages: int):
    """Background task: run scrapers."""
    db = next(get_db())
    try:
        scrapers = []
        if scraper_name is None or scraper_name == "bayut":
            scrapers.append(BayutScraper(db))
        if scraper_name is None or scraper_name == "dubizzle":
            scrapers.append(DubizzleScraper(db))
        if scraper_name is None or scraper_name == "propertyfinder":
            scrapers.append(PropertyFinderScraper(db))

        for scraper in scrapers:
            try:
                await scraper.scrape_all(max_pages=max_pages)
            except Exception as e:
                logger.error(f"Scraper {scraper.source_name} failed: {e}")
            finally:
                await scraper.close()
    finally:
        db.close()


def _run_analysis():
    """Background task: run analysis."""
    db = next(get_db())
    try:
        engine = AnalysisEngine(db)
        engine.calculate_market_stats()
        engine.score_deals()

        # AI-analyze top deals
        top = engine.get_top_deals(limit=settings.deal_score_top_n)
        if top and settings.anthropic_api_key:
            analyzer = AIAnalyzer(db)
            analyzer.analyze_top_deals(top)
    finally:
        db.close()


@app.post("/api/scrape")
async def trigger_scrape(
    background_tasks: BackgroundTasks,
    source: str | None = None,
    max_pages: int = Query(10, ge=1, le=50),
):
    """Trigger a scrape run. Optionally specify source (bayut, dubizzle, propertyfinder)."""
    background_tasks.add_task(asyncio.create_task, _run_scraper(source, max_pages))
    return {"status": "started", "source": source or "all", "max_pages": max_pages}


@app.post("/api/analyze")
async def trigger_analysis(background_tasks: BackgroundTasks):
    """Trigger market stats calculation, deal scoring, and AI analysis."""
    background_tasks.add_task(_run_analysis)
    return {"status": "started"}


@app.post("/api/ai-analyze/{property_id}")
def ai_analyze_property(property_id: int, db: Session = Depends(get_db)):
    """Run AI analysis on a specific property."""
    prop = db.query(Property).filter(Property.id == property_id).first()
    if not prop:
        return JSONResponse(status_code=404, content={"error": "Property not found"})

    analyzer = AIAnalyzer(db)
    analysis = analyzer._analyze_single(prop)
    if analysis:
        prop.ai_analysis = analysis
        prop.ai_analyzed_at = datetime.utcnow()
        db.commit()
        return {"property_id": property_id, "analysis": analysis}
    return JSONResponse(status_code=500, content={"error": "AI analysis failed"})


@app.get("/api/market-overview")
def market_overview(db: Session = Depends(get_db)):
    """Get AI-generated market overview."""
    properties = db.query(Property).filter(Property.is_active == True).all()
    if not properties:
        return {"overview": "No properties in database. Run a scrape first."}

    analyzer = AIAnalyzer(db)
    overview = analyzer.analyze_market_overview(properties)
    return {"overview": overview or "AI analysis not available. Set ANTHROPIC_API_KEY."}


# --------------- CLI Entry ---------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
