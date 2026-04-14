from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, Text, Boolean, UniqueConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()


class Property(Base):
    __tablename__ = "properties"

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(50), nullable=False)  # bayut, dubizzle, propertyfinder
    source_id = Column(String(200), nullable=False)  # ID on the source platform
    url = Column(String(500))

    title = Column(String(500))
    description = Column(Text)
    price = Column(Float)
    currency = Column(String(10), default="AED")

    property_type = Column(String(50))  # apartment, villa, townhouse, etc.
    bedrooms = Column(Integer)
    bathrooms = Column(Integer)
    area_sqft = Column(Float)
    price_per_sqft = Column(Float)

    city = Column(String(100))  # dubai, abu-dhabi
    neighborhood = Column(String(200))
    location_full = Column(String(500))
    latitude = Column(Float)
    longitude = Column(Float)

    furnishing = Column(String(50))  # furnished, unfurnished, semi-furnished
    completion_status = Column(String(50))  # ready, off-plan
    listed_date = Column(DateTime)
    scraped_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    # Rental info (if available from the same listing or estimated)
    estimated_annual_rent = Column(Float)

    # Analysis fields (populated by analysis engine)
    deal_score = Column(Float)
    area_median_price = Column(Float)
    area_median_price_per_sqft = Column(Float)
    price_vs_median_pct = Column(Float)  # negative = below median (good deal)
    rental_yield_pct = Column(Float)
    ai_analysis = Column(Text)
    ai_analyzed_at = Column(DateTime)

    __table_args__ = (
        UniqueConstraint("source", "source_id", name="uq_source_listing"),
    )

    def to_dict(self):
        return {
            "id": self.id,
            "source": self.source,
            "source_id": self.source_id,
            "url": self.url,
            "title": self.title,
            "price": self.price,
            "currency": self.currency,
            "property_type": self.property_type,
            "bedrooms": self.bedrooms,
            "bathrooms": self.bathrooms,
            "area_sqft": self.area_sqft,
            "price_per_sqft": self.price_per_sqft,
            "city": self.city,
            "neighborhood": self.neighborhood,
            "location_full": self.location_full,
            "furnishing": self.furnishing,
            "completion_status": self.completion_status,
            "listed_date": self.listed_date.isoformat() if self.listed_date else None,
            "scraped_at": self.scraped_at.isoformat() if self.scraped_at else None,
            "deal_score": self.deal_score,
            "area_median_price": self.area_median_price,
            "area_median_price_per_sqft": self.area_median_price_per_sqft,
            "price_vs_median_pct": self.price_vs_median_pct,
            "rental_yield_pct": self.rental_yield_pct,
            "estimated_annual_rent": self.estimated_annual_rent,
            "ai_analysis": self.ai_analysis,
            "ai_analyzed_at": self.ai_analyzed_at.isoformat() if self.ai_analyzed_at else None,
        }


class MarketStats(Base):
    """Cached market statistics per neighborhood/property type combo."""
    __tablename__ = "market_stats"

    id = Column(Integer, primary_key=True, autoincrement=True)
    city = Column(String(100), nullable=False)
    neighborhood = Column(String(200), nullable=False)
    property_type = Column(String(50))
    bedrooms = Column(Integer)

    median_price = Column(Float)
    median_price_per_sqft = Column(Float)
    avg_price = Column(Float)
    avg_price_per_sqft = Column(Float)
    listing_count = Column(Integer)
    median_rent = Column(Float)

    calculated_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("city", "neighborhood", "property_type", "bedrooms",
                         name="uq_market_stats"),
    )


class AnalysisResult(Base):
    """Stores AI analysis run metadata."""
    __tablename__ = "analysis_runs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    run_type = Column(String(50))  # market_stats, deal_scoring, ai_analysis
    properties_analyzed = Column(Integer)
    started_at = Column(DateTime, default=datetime.utcnow)
    completed_at = Column(DateTime)
    status = Column(String(20), default="running")  # running, completed, failed
    notes = Column(Text)
