"""Deal analysis engine: market stats, price comparison, rental yield, deal scoring."""

import logging
from datetime import datetime
from statistics import median

from sqlalchemy import func
from sqlalchemy.orm import Session

from database.models import Property, MarketStats, AnalysisResult

logger = logging.getLogger(__name__)

# Estimated gross rental yields by area (AED annual rent / purchase price)
# These are rough market averages used when actual rent data isn't available
DUBAI_RENTAL_YIELDS = {
    "dubai marina": 0.065,
    "downtown dubai": 0.055,
    "business bay": 0.070,
    "jumeirah village circle": 0.080,
    "jumeirah lake towers": 0.075,
    "dubai hills estate": 0.055,
    "palm jumeirah": 0.045,
    "dubai creek harbour": 0.060,
    "al barsha": 0.065,
    "dubai silicon oasis": 0.080,
    "international city": 0.090,
    "dubai sports city": 0.075,
    "motor city": 0.070,
    "arabian ranches": 0.050,
    "damac hills": 0.060,
    "town square": 0.075,
    "mudon": 0.060,
}

ABU_DHABI_RENTAL_YIELDS = {
    "al reem island": 0.070,
    "al raha beach": 0.060,
    "saadiyat island": 0.055,
    "yas island": 0.065,
    "khalifa city": 0.070,
    "al reef": 0.075,
    "al ghadeer": 0.070,
    "masdar city": 0.065,
}

DEFAULT_YIELD = 0.065  # 6.5% default for unknown areas


class AnalysisEngine:
    def __init__(self, db: Session):
        self.db = db

    def calculate_market_stats(self) -> int:
        """Calculate median/avg prices per neighborhood + property type + bedroom combo."""
        run = AnalysisResult(run_type="market_stats", started_at=datetime.utcnow())
        self.db.add(run)
        self.db.commit()

        # Get all unique groupings
        groups = (
            self.db.query(
                Property.city,
                Property.neighborhood,
                Property.property_type,
                Property.bedrooms,
            )
            .filter(Property.is_active == True, Property.price > 0)
            .distinct()
            .all()
        )

        count = 0
        for city, neighborhood, prop_type, bedrooms in groups:
            if not neighborhood:
                continue

            # Get all prices for this group
            props = (
                self.db.query(Property)
                .filter(
                    Property.city == city,
                    Property.neighborhood == neighborhood,
                    Property.property_type == prop_type,
                    Property.bedrooms == bedrooms,
                    Property.is_active == True,
                    Property.price > 0,
                )
                .all()
            )

            if len(props) < 3:  # Need at least 3 listings for meaningful stats
                continue

            prices = [p.price for p in props]
            prices_per_sqft = [p.price_per_sqft for p in props if p.price_per_sqft]

            median_price = median(prices)
            avg_price = sum(prices) / len(prices)
            median_ppsf = median(prices_per_sqft) if prices_per_sqft else None
            avg_ppsf = sum(prices_per_sqft) / len(prices_per_sqft) if prices_per_sqft else None

            # Upsert market stats
            existing = (
                self.db.query(MarketStats)
                .filter(
                    MarketStats.city == city,
                    MarketStats.neighborhood == neighborhood,
                    MarketStats.property_type == prop_type,
                    MarketStats.bedrooms == bedrooms,
                )
                .first()
            )

            if existing:
                existing.median_price = median_price
                existing.avg_price = avg_price
                existing.median_price_per_sqft = median_ppsf
                existing.avg_price_per_sqft = avg_ppsf
                existing.listing_count = len(props)
                existing.calculated_at = datetime.utcnow()
            else:
                stat = MarketStats(
                    city=city,
                    neighborhood=neighborhood,
                    property_type=prop_type,
                    bedrooms=bedrooms,
                    median_price=median_price,
                    avg_price=avg_price,
                    median_price_per_sqft=median_ppsf,
                    avg_price_per_sqft=avg_ppsf,
                    listing_count=len(props),
                    calculated_at=datetime.utcnow(),
                )
                self.db.add(stat)

            count += 1

        self.db.commit()

        run.completed_at = datetime.utcnow()
        run.properties_analyzed = count
        run.status = "completed"
        self.db.commit()

        logger.info(f"Calculated market stats for {count} neighborhood/type/bedroom groups")
        return count

    def score_deals(self) -> int:
        """Score all active properties based on price vs median and rental yield."""
        run = AnalysisResult(run_type="deal_scoring", started_at=datetime.utcnow())
        self.db.add(run)
        self.db.commit()

        properties = (
            self.db.query(Property)
            .filter(Property.is_active == True, Property.price > 0)
            .all()
        )

        scored = 0
        for prop in properties:
            score = self._calculate_deal_score(prop)
            if score is not None:
                prop.deal_score = score
                scored += 1

        self.db.commit()

        run.completed_at = datetime.utcnow()
        run.properties_analyzed = scored
        run.status = "completed"
        self.db.commit()

        logger.info(f"Scored {scored} properties")
        return scored

    def _calculate_deal_score(self, prop: Property) -> float | None:
        """
        Calculate deal score (0-100). Higher = better deal.

        Components:
        - Price vs median (40% weight): how far below area median
        - Price per sqft vs median (30% weight): value for space
        - Rental yield (30% weight): income potential
        """
        score_components = []
        weights = []

        # 1. Price vs area median (40%)
        stats = (
            self.db.query(MarketStats)
            .filter(
                MarketStats.city == prop.city,
                MarketStats.neighborhood == prop.neighborhood,
                MarketStats.property_type == prop.property_type,
                MarketStats.bedrooms == prop.bedrooms,
            )
            .first()
        )

        if stats and stats.median_price:
            pct_diff = ((prop.price - stats.median_price) / stats.median_price) * 100
            prop.area_median_price = stats.median_price
            prop.price_vs_median_pct = round(pct_diff, 2)

            # Score: 20% below median = 100, at median = 50, 20% above = 0
            price_score = max(0, min(100, 50 - (pct_diff * 2.5)))
            score_components.append(price_score)
            weights.append(0.40)

        # 2. Price per sqft vs median (30%)
        if stats and stats.median_price_per_sqft and prop.price_per_sqft:
            prop.area_median_price_per_sqft = stats.median_price_per_sqft
            ppsf_diff = (
                (prop.price_per_sqft - stats.median_price_per_sqft)
                / stats.median_price_per_sqft
            ) * 100
            ppsf_score = max(0, min(100, 50 - (ppsf_diff * 2.5)))
            score_components.append(ppsf_score)
            weights.append(0.30)

        # 3. Rental yield (30%)
        rental_yield = self._estimate_rental_yield(prop)
        if rental_yield:
            prop.rental_yield_pct = round(rental_yield * 100, 2)
            if not prop.estimated_annual_rent:
                prop.estimated_annual_rent = round(prop.price * rental_yield, 0)

            # Score: 10%+ yield = 100, 5% = 50, 0% = 0
            yield_score = max(0, min(100, rental_yield * 1000))
            score_components.append(yield_score)
            weights.append(0.30)

        if not score_components:
            return None

        # Normalize weights
        total_weight = sum(weights)
        weighted_score = sum(s * w for s, w in zip(score_components, weights)) / total_weight

        return round(weighted_score, 1)

    def _estimate_rental_yield(self, prop: Property) -> float | None:
        """Estimate rental yield from known area data or defaults."""
        if prop.estimated_annual_rent and prop.price:
            return prop.estimated_annual_rent / prop.price

        neighborhood = (prop.neighborhood or "").lower().strip()

        if prop.city == "dubai":
            for area, yield_pct in DUBAI_RENTAL_YIELDS.items():
                if area in neighborhood or neighborhood in area:
                    return yield_pct
        elif prop.city in ("abu-dhabi", "abu dhabi"):
            for area, yield_pct in ABU_DHABI_RENTAL_YIELDS.items():
                if area in neighborhood or neighborhood in area:
                    return yield_pct

        return DEFAULT_YIELD

    def get_top_deals(self, limit: int = 20, city: str | None = None) -> list[Property]:
        """Get top-scored deals."""
        query = (
            self.db.query(Property)
            .filter(Property.is_active == True, Property.deal_score.isnot(None))
        )
        if city:
            query = query.filter(Property.city == city)

        return query.order_by(Property.deal_score.desc()).limit(limit).all()

    def get_summary_stats(self) -> dict:
        """Get overall database and analysis summary."""
        total = self.db.query(func.count(Property.id)).filter(Property.is_active == True).scalar()
        scored = (
            self.db.query(func.count(Property.id))
            .filter(Property.is_active == True, Property.deal_score.isnot(None))
            .scalar()
        )
        ai_analyzed = (
            self.db.query(func.count(Property.id))
            .filter(Property.ai_analysis.isnot(None))
            .scalar()
        )

        by_city = dict(
            self.db.query(Property.city, func.count(Property.id))
            .filter(Property.is_active == True)
            .group_by(Property.city)
            .all()
        )

        by_source = dict(
            self.db.query(Property.source, func.count(Property.id))
            .filter(Property.is_active == True)
            .group_by(Property.source)
            .all()
        )

        return {
            "total_listings": total,
            "scored_listings": scored,
            "ai_analyzed": ai_analyzed,
            "by_city": by_city,
            "by_source": by_source,
        }
