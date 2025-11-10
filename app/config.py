"""Application Configuration"""
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Database
    DATABASE_URL: str
    
    # Redis
    REDIS_URL: str = "redis://localhost:6379"
    CACHE_TTL_SECONDS: int = 3600
    
    # Apple Music API
    APPLE_TEAM_ID: str
    APPLE_KEY_ID: str
    APPLE_PRIVATE_KEY: str
    
    # YouTube Data API
    YOUTUBE_API_KEY: str
    
    # Spotify Web API
    SPOTIFY_CLIENT_ID: str
    SPOTIFY_CLIENT_SECRET: str
    
    # Optional APIs
    LASTFM_API_KEY: Optional[str] = None
    LASTFM_ENABLED: bool = False
    BEATPORT_API_KEY: Optional[str] = None
    BEATPORT_ENABLED: bool = False
    
    # Application Settings
    DEFAULT_REGION: str = "DE"
    DEFAULT_GENRE: str = "techhouse"
    LOG_LEVEL: str = "INFO"
    ENVIRONMENT: str = "development"
    
    # Rate Limits
    APPLE_MUSIC_REQUESTS_PER_MINUTE: int = 30
    YOUTUBE_DAILY_QUOTA: int = 10000
    SPOTIFY_REQUESTS_PER_SECOND: int = 10
    
    # Feature Flags
    ENABLE_MUSICBRAINZ_ENRICHMENT: bool = True
    ENABLE_BUY_LINKS: bool = True
    ENABLE_TREND_VELOCITY: bool = False
    
    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()