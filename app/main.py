"""FastAPI Main Application"""
from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.responses import HTMLResponse, Response, FileResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from typing import Optional, List
import asyncpg
from datetime import date, datetime
import logging
import time
import os

from .config import settings
from .models import (
    TrendsResponse, RefreshResponse, HealthResponse,
    AggregatedTrack, Track, BuyLink
)
from .providers import AppleMusicProvider, YouTubeProvider, SpotifyProvider
from .services import DeduplicationService, ScoringService

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Create FastAPI app
app = FastAPI(
    title="Music Trend Panel",
    description="Aggregated music trends from Apple Music, YouTube & Spotify",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Templates
templates = Jinja2Templates(directory="app/templates")

# Static files
if os.path.exists("app/static"):
    app.mount("/static", StaticFiles(directory="app/static"), name="static")


# Database connection pool
@app.on_event("startup")
async def startup():
    """Initialize database connection pool"""
    try:
        app.state.db_pool = await asyncpg.create_pool(
            settings.DATABASE_URL,
            min_size=5,
            max_size=20,
            command_timeout=30
        )
        logger.info("Database connection pool created")
    except Exception as e:
        logger.error(f"Failed to create database pool: {e}")
        raise


@app.on_event("shutdown")
async def shutdown():
    """Close database connection pool"""
    if hasattr(app.state, 'db_pool'):
        await app.state.db_pool.close()
        logger.info("Database connection pool closed")


# Dependency to get database connection
async def get_db():
    async with app.state.db_pool.acquire() as conn:
        yield conn


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Render web UI"""
    return templates.TemplateResponse("index.html", {"request": request})


@app.get("/api/trends", response_model=TrendsResponse)
async def get_trends(
    region: str = Query("DE", regex="^[A-Z]{2}$", description="ISO 3166-1 alpha-2 country code"),
    genre: Optional[str] = Query(None, description="Genre filter (techhouse, pop, etc.)"),
    chart_date: Optional[date] = Query(None, description="Chart date (default: today)"),
    limit: int = Query(50, ge=1, le=100, description="Number of results"),
    db = Depends(get_db)
):
    """
    Get aggregated trend tracks from all providers
    
    Returns tracks ranked by combined score from multiple sources.
    """
    target_date = chart_date or date.today()
    
    # Build query to fetch tracks with trend data
    query = """
        WITH track_trends AS (
            SELECT 
                t.id, t.title, t.artist, t.artwork_url,
                te.provider, te.rank, te.score, te.metadata
            FROM tracks t
            JOIN trend_entries te ON t.id = te.track_id
            WHERE te.region = $1 
              AND te.chart_date = $2
              AND ($3::TEXT IS NULL OR te.genre = $3)
        ),
        aggregated AS (
            SELECT 
                id, title, artist, artwork_url,
                JSON_AGG(JSON_BUILD_OBJECT(
                    'provider', provider,
                    'rank', rank,
                    'score', score,
                    'metadata', metadata
                )) as trend_data,
                ARRAY_AGG(DISTINCT provider) as sources
            FROM track_trends
            GROUP BY id, title, artist, artwork_url
        )
        SELECT * FROM aggregated
        LIMIT $4
    """
    
    rows = await db.fetch(query, region, target_date, genre, limit * 2)  # Fetch more for scoring
    
    if not rows:
        return TrendsResponse(
            results=[],
            meta={
                'region': region,
                'genre': genre,
                'date': str(target_date),
                'count': 0
            }
        )
    
    # Score and rank tracks
    scoring = ScoringService()
    tracks_with_scores = []
    
    for row in rows:
        track_data = {
            'track': {
                'id': row['id'],
                'title': row['title'],
                'artist': row['artist'],
                'artwork_url': row['artwork_url']
            },
            'trend_data': row['trend_data'],
            'sources': row['sources']
        }
        tracks_with_scores.append(track_data)
    
    # Rank by combined score
    ranked_tracks = scoring.rank_tracks(tracks_with_scores)
    
    # Limit to requested amount
    ranked_tracks = ranked_tracks[:limit]
    
    # Fetch buy links
    results = []
    for track_data in ranked_tracks:
        track_id = track_data['track']['id']
        
        # Get buy links
        buy_links_query = "SELECT platform, url, verified FROM buy_links WHERE track_id = $1 LIMIT 5"
        buy_links = await db.fetch(buy_links_query, track_id)
        
        results.append({
            'track': track_data['track'],
            'combined_score': track_data['combined_score'],
            'rank': track_data['rank'],
            'sources': track_data['sources'],
            'trend_data': track_data['trend_data'],
            'buy_links': [dict(bl) for bl in buy_links]
        })
    
    return TrendsResponse(
        results=results,
        meta={
            'region': region,
            'genre': genre or 'all',
            'date': str(target_date),
            'count': len(results)
        }
    )


@app.post("/api/refresh", response_model=RefreshResponse)
async def refresh_trends(
    region: str = Query("DE", regex="^[A-Z]{2}$"),
    genre: Optional[str] = Query(None),
    force: bool = Query(False, description="Force refresh even if data exists"),
    db = Depends(get_db)
):
    """
    Refresh trend data from all providers
    
    Fetches latest charts from Apple Music, YouTube, and Spotify.
    """
    start_time = time.time()
    
    # Check if refresh is needed
    if not force:
        check_query = """
            SELECT COUNT(*) as count FROM trend_entries 
            WHERE region = $1 AND chart_date = CURRENT_DATE
        """
        result = await db.fetchrow(check_query, region)
        if result['count'] > 0:
            return RefreshResponse(
                status="skipped",
                tracks_processed=result['count'],
                providers=[],
                duration_seconds=0.0,
                errors=["Data already exists for today. Use force=true to refresh."]
            )
    
    # Initialize services
    dedupe = DeduplicationService(app.state.db_pool, settings.ENABLE_MUSICBRAINZ_ENRICHMENT)
    
    # Initialize providers
    providers = []
    provider_names = []
    
    try:
        apple = AppleMusicProvider(
            settings.APPLE_TEAM_ID,
            settings.APPLE_KEY_ID,
            settings.APPLE_PRIVATE_KEY
        )
        providers.append((apple, 'apple_music'))
        provider_names.append('apple_music')
    except Exception as e:
        logger.error(f"Failed to initialize Apple Music provider: {e}")
    
    try:
        youtube = YouTubeProvider(settings.YOUTUBE_API_KEY)
        providers.append((youtube, 'youtube'))
        provider_names.append('youtube')
    except Exception as e:
        logger.error(f"Failed to initialize YouTube provider: {e}")
    
    try:
        spotify = SpotifyProvider(
            settings.SPOTIFY_CLIENT_ID,
            settings.SPOTIFY_CLIENT_SECRET
        )
        providers.append((spotify, 'spotify'))
        provider_names.append('spotify')
    except Exception as e:
        logger.error(f"Failed to initialize Spotify provider: {e}")
    
    if not providers:
        raise HTTPException(
            status_code=500,
            detail="No providers could be initialized. Check API credentials."
        )
    
    total_tracks = 0
    errors = []
    
    # Fetch from each provider
    for provider, provider_name in providers:
        try:
            logger.info(f"Fetching from {provider_name}...")
            tracks = await provider.fetch_charts(region, genre)
            
            # Process each track
            for track_data in tracks:
                try:
                    # Deduplicate
                    track_id = await dedupe.find_or_create_track(track_data)
                    
                    # Insert trend entry
                    insert_query = """
                        INSERT INTO trend_entries (
                            track_id, provider, rank, score, region, genre, metadata, chart_date
                        )
                        VALUES ($1, $2, $3, $4, $5, $6, $7, CURRENT_DATE)
                        ON CONFLICT (track_id, provider, region, genre, chart_date) 
                        DO UPDATE SET 
                            rank = EXCLUDED.rank,
                            score = EXCLUDED.score,
                            metadata = EXCLUDED.metadata
                    """
                    
                    await db.execute(
                        insert_query,
                        track_id,
                        track_data['provider'],
                        track_data.get('rank'),
                        track_data.get('rank', 50),
                        region,
                        genre or 'all',
                        track_data.get('metadata', {})
                    )
                    
                    total_tracks += 1
                    
                except Exception as e:
                    logger.error(f"Failed to process track: {e}")
                    errors.append(f"Track processing error: {str(e)}")
            
            await provider.close()
            
        except Exception as e:
            logger.error(f"Provider {provider_name} failed: {e}")
            errors.append(f"{provider_name}: {str(e)}")
    
    await dedupe.close()
    
    duration = time.time() - start_time
    
    return RefreshResponse(
        status="success" if total_tracks > 0 else "failed",
        tracks_processed=total_tracks,
        providers=provider_names,
        duration_seconds=round(duration, 2),
        errors=errors
    )


@app.get("/api/trends/{track_id}/buy-links")
async def get_buy_links(
    track_id: int,
    db = Depends(get_db)
):
    """
    Get or generate buy links for a track
    """
    # Check if track exists
    track = await db.fetchrow("SELECT * FROM tracks WHERE id = $1", track_id)
    if not track:
        raise HTTPException(status_code=404, detail="Track not found")
    
    # Check existing links
    existing_links = await db.fetch(
        "SELECT platform, url, verified FROM buy_links WHERE track_id = $1",
        track_id
    )
    
    if existing_links:
        return {
            'track_id': track_id,
            'links': [dict(link) for link in existing_links]
        }
    
    # Generate search links
    search_query = f"{track['artist']} {track['title']}".replace(' ', '+')
    
    links = [
        {
            'platform': 'beatport',
            'url': f"https://www.beatport.com/search?q={search_query}",
            'verified': False
        },
        {
            'platform': 'traxsource',
            'url': f"https://www.traxsource.com/search?term={search_query}",
            'verified': False
        },
        {
            'platform': 'bandcamp',
            'url': f"https://bandcamp.com/search?q={search_query}",
            'verified': False
        },
        {
            'platform': 'juno',
            'url': f"https://www.junodownload.com/search/?q%5Ball%5D%5B%5D={search_query}",
            'verified': False
        }
    ]
    
    # Cache in database
    for link in links:
        await db.execute(
            """
            INSERT INTO buy_links (track_id, platform, url, verified) 
            VALUES ($1, $2, $3, $4) 
            ON CONFLICT DO NOTHING
            """,
            track_id, link['platform'], link['url'], link['verified']
        )
    
    return {'track_id': track_id, 'links': links}


@app.get("/api/export")
async def export_trends(
    format: str = Query("csv", regex="^(csv|m3u|json)$"),
    region: str = Query("DE", regex="^[A-Z]{2}$"),
    genre: Optional[str] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    db = Depends(get_db)
):
    """
    Export trends in various formats
    
    - **csv**: Spreadsheet format
    - **m3u**: Playlist format (with preview URLs)
    - **json**: Raw JSON data
    """
    # Get trends using main endpoint logic
    trends_data = await get_trends(
        region=region,
        genre=genre,
        chart_date=None,
        limit=limit,
        db=db
    )
    
    if format == "csv":
        import csv
        from io import StringIO
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Rank', 'Artist', 'Title', 'Score', 'Sources', 'Providers'])
        
        for item in trends_data.results:
            writer.writerow([
                item.rank,
                item.track['artist'],
                item.track['title'],
                item.combined_score,
                len(item.sources),
                ','.join(item.sources)
            ])
        
        return Response(
            content=output.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": f"attachment; filename=trends_{region}_{date.today()}.csv"}
        )
    
    elif format == "m3u":
        lines = ["#EXTM3U\n"]
        
        for item in trends_data.results:
            # Find preview URL from metadata
            preview_url = None
            for td in item.trend_data:
                if td.get('metadata', {}).get('preview_url'):
                    preview_url = td['metadata']['preview_url']
                    break
                elif td.get('metadata', {}).get('url'):
                    # Use streaming URL as fallback
                    preview_url = td['metadata']['url']
                    break
            
            if preview_url:
                lines.append(f"#EXTINF:-1,{item.track['artist']} - {item.track['title']}\n")
                lines.append(f"{preview_url}\n")
        
        return Response(
            content=''.join(lines),
            media_type="audio/x-mpegurl",
            headers={"Content-Disposition": f"attachment; filename=trends_{region}_{date.today()}.m3u"}
        )
    
    else:  # json
        return trends_data


@app.get("/health", response_model=HealthResponse)
async def health_check():
    """
    Health check endpoint
    """
    db_healthy = False
    redis_healthy = False
    
    # Check database
    try:
        async with app.state.db_pool.acquire() as conn:
            await conn.fetchval("SELECT 1")
        db_healthy = True
    except Exception as e:
        logger.error(f"Database health check failed: {e}")
    
    # Check Redis (if configured)
    # TODO: Implement Redis health check
    redis_healthy = True  # Placeholder
    
    return HealthResponse(
        status="healthy" if (db_healthy and redis_healthy) else "degraded",
        version="1.0.0",
        database=db_healthy,
        redis=redis_healthy,
        timestamp=datetime.now()
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)