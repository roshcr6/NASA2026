"""Application settings — loaded from environment variables or .env file."""
from __future__ import annotations

from functools import lru_cache
from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # IRSA SIA v2 endpoint (public, no key required)
    irsa_sia_url: str = "https://irsa.ipac.caltech.edu/SIA"

    # IRSA IBE data base URL for cutouts
    irsa_ibe_url: str = "https://irsa.ipac.caltech.edu/ibe/data/spherex"

    # Preferred release; will fall back to spherex_qr2 if qr3 unavailable
    preferred_release: str = "spherex_qr3"
    fallback_release: str = "spherex_qr2"

    # Cache directory for generated previews (relative to backend dir)
    cache_dir: str = "cache"

    # Max parallel HTTP requests to IRSA
    max_concurrent_requests: int = 6

    # Max cutout size in degrees (server-side guard)
    max_cutout_deg: float = 0.5

    # Default cutout size in degrees
    default_cutout_deg: float = 0.1

    # HTTP timeout in seconds
    http_timeout: float = 30.0

    # Allowed CORS origins (comma-separated in env; list here)
    cors_origins: List[str] = ["http://localhost:3000", "http://127.0.0.1:3000"]

    # Debug mode (enables /docs)
    debug: bool = True

    # Preview image max dimension (pixels)
    preview_max_px: int = 512

    # Cache TTL in seconds for SIA metadata
    metadata_cache_ttl: int = 3600  # 1 hour

    # Cache TTL for generated previews
    preview_cache_ttl: int = 86400  # 24 hours


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
