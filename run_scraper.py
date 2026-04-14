"""CLI script to run scrapers and analysis."""

import asyncio
import argparse
import logging
import sys

from database.db import engine, SessionLocal
from database.models import Base
from scrapers.bayut import BayutScraper
from scrapers.dubizzle import DubizzleScraper
from scrapers.propertyfinder import PropertyFinderScraper
from analysis.metrics import AnalysisEngine
from analysis.ai_analyzer import AIAnalyzer
from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)

SCRAPERS = {
    "bayut": BayutScraper,
    "dubizzle": DubizzleScraper,
    "propertyfinder": PropertyFinderScraper,
}


async def run_scrapers(sources: list[str], max_pages: int):
    """Run selected scrapers."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    total = 0
    try:
        for name in sources:
            cls = SCRAPERS.get(name)
            if not cls:
                logger.warning(f"Unknown scraper: {name}")
                continue

            scraper = cls(db)
            try:
                count = await scraper.scrape_all(max_pages=max_pages)
                total += count
                logger.info(f"[{name}] Total: {count} listings saved")
            except Exception as e:
                logger.error(f"[{name}] Failed: {e}")
            finally:
                await scraper.close()
    finally:
        db.close()

    return total


def run_analysis(ai: bool = True):
    """Run market stats, deal scoring, and optionally AI analysis."""
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()

    try:
        engine_a = AnalysisEngine(db)

        logger.info("Calculating market stats...")
        stats_count = engine_a.calculate_market_stats()
        logger.info(f"Market stats calculated for {stats_count} groups")

        logger.info("Scoring deals...")
        scored = engine_a.score_deals()
        logger.info(f"Scored {scored} properties")

        if ai:
            logger.info("Running AI analysis on top deals via Ollama...")
            top_deals = engine_a.get_top_deals(limit=settings.deal_score_top_n)
            analyzer = AIAnalyzer(db)
            analyzed = analyzer.analyze_top_deals(top_deals)
            logger.info(f"AI analyzed {analyzed} deals")

        # Print summary
        summary = engine_a.get_summary_stats()
        print("\n=== Summary ===")
        print(f"Total listings:  {summary['total_listings']}")
        print(f"Scored:          {summary['scored_listings']}")
        print(f"AI analyzed:     {summary['ai_analyzed']}")
        print(f"By city:         {summary['by_city']}")
        print(f"By source:       {summary['by_source']}")
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="Property Deal Finder - CLI")
    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Scrape command
    scrape_parser = subparsers.add_parser("scrape", help="Run property scrapers")
    scrape_parser.add_argument(
        "--source", "-s",
        choices=["bayut", "dubizzle", "propertyfinder", "all"],
        default="all",
        help="Which source to scrape (default: all)",
    )
    scrape_parser.add_argument(
        "--max-pages", "-p",
        type=int,
        default=10,
        help="Max pages to scrape per city (default: 10)",
    )

    # Analyze command
    analyze_parser = subparsers.add_parser("analyze", help="Run deal analysis")
    analyze_parser.add_argument(
        "--no-ai",
        action="store_true",
        help="Skip AI analysis",
    )

    # Full run command
    subparsers.add_parser("run", help="Scrape all sources then analyze")

    # Server command
    server_parser = subparsers.add_parser("server", help="Start the web dashboard")
    server_parser.add_argument("--port", type=int, default=8000)
    server_parser.add_argument("--host", default="0.0.0.0")

    args = parser.parse_args()

    if args.command == "scrape":
        sources = list(SCRAPERS.keys()) if args.source == "all" else [args.source]
        total = asyncio.run(run_scrapers(sources, args.max_pages))
        print(f"\nDone. {total} total listings saved.")

    elif args.command == "analyze":
        run_analysis(ai=not args.no_ai)

    elif args.command == "run":
        print("=== Step 1: Scraping all sources ===")
        total = asyncio.run(run_scrapers(list(SCRAPERS.keys()), max_pages=10))
        print(f"Scraping complete: {total} listings\n")

        print("=== Step 2: Running analysis ===")
        run_analysis(ai=True)

    elif args.command == "server":
        import uvicorn
        print(f"Starting server at http://{args.host}:{args.port}")
        uvicorn.run("main:app", host=args.host, port=args.port, reload=True)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()
