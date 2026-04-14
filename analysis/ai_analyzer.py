"""AI-powered deal analysis using Ollama (local LLM)."""

import logging
from datetime import datetime

import httpx
from sqlalchemy.orm import Session

from database.models import Property
from config import settings

logger = logging.getLogger(__name__)


class AIAnalyzer:
    def __init__(self, db: Session):
        self.db = db
        self.base_url = settings.ollama_base_url.rstrip("/")
        self.model = settings.ollama_model
        self._available = None

    def _check_ollama(self) -> bool:
        """Check if Ollama is running and the model is available."""
        if self._available is not None:
            return self._available
        try:
            resp = httpx.get(f"{self.base_url}/api/tags", timeout=5.0)
            resp.raise_for_status()
            models = [m["name"] for m in resp.json().get("models", [])]
            # Match model name with or without :latest tag
            self._available = any(
                self.model in m or m.startswith(self.model + ":")
                for m in models
            )
            if not self._available:
                logger.warning(
                    f"Ollama is running but model '{self.model}' not found. "
                    f"Available: {models}. Run: ollama pull {self.model}"
                )
            return self._available
        except Exception as e:
            logger.warning(f"Ollama not reachable at {self.base_url}: {e}")
            self._available = False
            return False

    def _chat(self, prompt: str, max_tokens: int = 1000) -> str | None:
        """Send a chat request to Ollama and return the response text."""
        try:
            resp = httpx.post(
                f"{self.base_url}/api/chat",
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "options": {
                        "num_predict": max_tokens,
                        "temperature": 0.7,
                    },
                },
                timeout=120.0,
            )
            resp.raise_for_status()
            return resp.json().get("message", {}).get("content", "")
        except httpx.TimeoutException:
            logger.error("Ollama request timed out (120s)")
            return None
        except Exception as e:
            logger.error(f"Ollama request failed: {e}")
            return None

    def analyze_top_deals(self, deals: list[Property]) -> int:
        """Run AI analysis on a list of top-scored deals."""
        if not self._check_ollama():
            logger.warning("AI analyzer not available - skipping")
            return 0

        analyzed = 0
        for prop in deals:
            if prop.ai_analysis and prop.ai_analyzed_at:
                age = (datetime.utcnow() - prop.ai_analyzed_at).total_seconds()
                if age < 86400:
                    continue

            analysis = self._analyze_single(prop)
            if analysis:
                prop.ai_analysis = analysis
                prop.ai_analyzed_at = datetime.utcnow()
                self.db.commit()
                analyzed += 1

        logger.info(f"AI analyzed {analyzed} deals")
        return analyzed

    def _analyze_single(self, prop: Property) -> str | None:
        """Generate AI analysis for a single property."""
        prompt = self._build_prompt(prop)
        return self._chat(prompt, max_tokens=1000)

    def _build_prompt(self, prop: Property) -> str:
        """Build the analysis prompt for a property."""
        price_vs_median = ""
        if prop.price_vs_median_pct is not None:
            direction = "below" if prop.price_vs_median_pct < 0 else "above"
            price_vs_median = (
                f"- Price vs area median: {abs(prop.price_vs_median_pct):.1f}% {direction} "
                f"(area median: AED {prop.area_median_price:,.0f})"
            )

        ppsf_info = ""
        if prop.price_per_sqft and prop.area_median_price_per_sqft:
            ppsf_info = (
                f"- Price/sqft: AED {prop.price_per_sqft:,.0f} "
                f"(area median: AED {prop.area_median_price_per_sqft:,.0f}/sqft)"
            )

        yield_info = ""
        if prop.rental_yield_pct:
            yield_info = f"- Estimated rental yield: {prop.rental_yield_pct:.1f}%"
            if prop.estimated_annual_rent:
                yield_info += f" (est. annual rent: AED {prop.estimated_annual_rent:,.0f})"

        return f"""You are a UAE real estate investment analyst. Analyze this property deal and provide a concise investment assessment.

## Property Details
- **Title:** {prop.title}
- **Price:** AED {prop.price:,.0f}
- **Type:** {prop.property_type}
- **Bedrooms:** {prop.bedrooms} | **Bathrooms:** {prop.bathrooms}
- **Area:** {prop.area_sqft:,.0f} sqft
- **Location:** {prop.neighborhood}, {prop.city}
- **Furnishing:** {prop.furnishing or 'Not specified'}
- **Completion:** {prop.completion_status or 'Not specified'}
- **Source:** {prop.source}
- **Deal Score:** {prop.deal_score}/100

## Market Analysis
{price_vs_median}
{ppsf_info}
{yield_info}

## Instructions
Provide a brief investment analysis covering:
1. **Deal Rating** (Strong Buy / Buy / Hold / Avoid) and why
2. **Key Strengths** of this deal (2-3 bullet points)
3. **Risk Factors** to watch (2-3 bullet points)
4. **Rental Potential** assessment
5. **One-line verdict** summarizing the opportunity

Keep it concise and actionable. Focus on UAE market specifics (DLD fees, service charges, area trends).
"""

    def analyze_market_overview(self, properties: list[Property]) -> str | None:
        """Generate an AI-powered market overview from current listings."""
        if not self._check_ollama():
            return None

        cities = {}
        for p in properties:
            city = p.city or "unknown"
            if city not in cities:
                cities[city] = {"count": 0, "prices": [], "scores": []}
            cities[city]["count"] += 1
            cities[city]["prices"].append(p.price)
            if p.deal_score:
                cities[city]["scores"].append(p.deal_score)

        summary_lines = []
        for city, data in cities.items():
            avg_price = sum(data["prices"]) / len(data["prices"]) if data["prices"] else 0
            avg_score = sum(data["scores"]) / len(data["scores"]) if data["scores"] else 0
            summary_lines.append(
                f"- {city.title()}: {data['count']} listings, "
                f"avg price AED {avg_price:,.0f}, avg deal score {avg_score:.1f}"
            )

        prompt = f"""You are a UAE real estate market analyst. Based on the following current listing data, provide a brief market overview.

## Current Database
{chr(10).join(summary_lines)}

Total listings: {len(properties)}

Provide a 3-4 paragraph market overview covering:
1. Current market conditions in Dubai and Abu Dhabi
2. Where the best value deals are concentrated
3. Investment recommendations for buyers right now
4. Any caution areas or overpriced segments

Keep it concise and data-driven.
"""
        return self._chat(prompt, max_tokens=1500)
