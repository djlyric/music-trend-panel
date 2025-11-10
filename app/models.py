"""Pydantic Models for API"""
from pydantic import BaseModel, Field, HttpUrl
from datetime import date, datetime
from typing import Optional, List, Dict, Any
from enum import Enum


class Provider(str, Enum):
    """Music data providers"""
    APPLE_MUSIC = "apple_music"
    YOUTUBE = "youtube"
    SPOTIFY = "spotify"
    LASTFM = "lastfm"


class Platform(str, Enum):
    """Purchase/streaming platforms"""
    BEATPORT = "beatport"
    TRAXSOURCE = "traxsource"
    BANDCAMP = "bandcamp"
    JUNO = "juno"
    APPLE_MUSIC = "apple_music"
    SPOTIFY = "spotify"


class TrackBase(BaseModel):
    """Base track model"""
    title: str = Field(..., max_length=500)
    artist: str = Field(..., max_length=500)
    isrc: Optional[str] = Field(None, max_length=12)
    duration_ms: Optional[int] = Field(None, ge=0)
    artwork_url: Optional[str] = None


class Track(TrackBase):
    """Complete track model with metadata"""
    id: int
    normalized_title: Optional[str] = None
    normalized_artist: Optional[str] = None
    musicbrainz_recording_id: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TrendEntry(BaseModel):
    """Provider-specific trend data"""
    id: int
    track_id: int
    provider: Provider
    rank: Optional[int] = Field(None, ge=1)
    score: float = Field(..., ge=0, le=100)
    region: str = Field(..., max_length=10)
    genre: str = Field(..., max_length=100)
    chart_date: date
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: datetime

    class Config:
        from_attributes = True


class BuyLink(BaseModel):
    """Purchase/streaming link"""
    platform: Platform
    url: str
    verified: bool = False
    last_checked: Optional[datetime] = None


class AggregatedTrack(BaseModel):
    """Aggregated track with combined data from all sources"""
    track: Track
    combined_score: float
    rank: int
    sources: List[str]
    trend_data: List[Dict[str, Any]]
    buy_links: List[BuyLink]


class TrendsResponse(BaseModel):
    """API response for trends endpoint"""
    results: List[AggregatedTrack]
    meta: Dict[str, Any]


class RefreshRequest(BaseModel):
    """Request body for refresh endpoint"""
    region: str = Field("DE", regex="^[A-Z]{2}$")
    genre: Optional[str] = None
    force: bool = False


class RefreshResponse(BaseModel):
    """Response from refresh endpoint"""
    status: str
    tracks_processed: int
    providers: List[str]
    duration_seconds: float
    errors: List[str] = Field(default_factory=list)


class HealthResponse(BaseModel):
    """Health check response"""
    status: str
    version: str
    database: bool
    redis: bool
    timestamp: datetime