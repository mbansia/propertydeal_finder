import os
from pydantic_settings import BaseSettings
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    # Ollama
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.1"

    database_url: str = "sqlite:///./data/properties.db"
    scrape_interval_hours: int = 6
    max_concurrent_requests: int = 3
    request_delay_seconds: float = 2.0

    # Scraper targets
    cities: list[str] = ["dubai", "abu-dhabi"]
    property_types: list[str] = ["apartment", "villa", "townhouse", "penthouse", "duplex"]

    # Analysis
    deal_score_top_n: int = 20  # Top N deals to send to AI for deep analysis

    class Config:
        env_file = ".env"


settings = Settings()
