"""Track Deduplication and Enrichment Service"""
import re
import unicodedata
from typing import Dict, Any, Optional
from fuzzywuzzy import fuzz
import httpx
import logging

logger = logging.getLogger(__name__)


class DeduplicationService:
    """Service for finding and matching duplicate tracks across providers"""
    
    def __init__(self, db_pool, enable_musicbrainz: bool = True):
        self.db = db_pool
        self.enable_musicbrainz = enable_musicbrainz
        self.musicbrainz_client = httpx.AsyncClient(
            base_url="https://musicbrainz.org/ws/2",
            headers={'User-Agent': 'MusicTrendPanel/1.0 (https://github.com/djlyric/music-trend-panel)'},
            timeout=10.0
        )
    
    def normalize_string(self, text: str) -> str:
        """Aggressively normalize string for matching
        
        - Converts to lowercase
        - Removes accents and diacritics
        - Removes special characters
        - Removes featuring/remix annotations
        - Normalizes whitespace
        """
        if not text:
            return ""
        
        # Unicode normalization (decompose and remove combining marks)
        text = unicodedata.normalize('NFKD', text)
        text = ''.join(c for c in text if not unicodedata.combining(c))
        
        # Lowercase
        text = text.lower()
        
        # Remove parenthetical content (remixes, versions, etc.)
        text = re.sub(r'\s*[\(\[].+?[\)\]]\s*', ' ', text)
        
        # Remove featuring annotations
        text = re.sub(r'\s+(feat\.?|ft\.?|featuring|with|vs\.?|&)\s+.+', '', text, flags=re.IGNORECASE)
        
        # Remove special characters except spaces
        text = re.sub(r'[^a-z0-9\s]', '', text)
        
        # Normalize whitespace
        text = re.sub(r'\s+', ' ', text).strip()
        
        return text
    
    async def find_or_create_track(self, track_data: Dict[str, Any]) -> int:
        """Find existing track or create new one
        
        Deduplication strategy:
        1. Exact match on normalized artist + title
        2. ISRC match (if available)
        3. Fuzzy match on normalized strings
        4. MusicBrainz enrichment (if enabled)
        5. Create new track
        
        Args:
            track_data: Normalized track dictionary from provider
            
        Returns:
            Track ID (new or existing)
        """
        normalized_title = self.normalize_string(track_data['title'])
        normalized_artist = self.normalize_string(track_data['artist'])
        
        if not normalized_title or not normalized_artist:
            logger.warning(f"Cannot deduplicate track with empty title/artist: {track_data}")
            # Still create it but skip matching
            return await self._create_track(track_data, normalized_title, normalized_artist)
        
        # 1. Exact normalized match
        query = """
            SELECT id FROM tracks 
            WHERE normalized_title = $1 AND normalized_artist = $2
            LIMIT 1
        """
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(query, normalized_title, normalized_artist)
            if row:
                logger.debug(f"Found exact match: track_id={row['id']}")
                await self._update_track_metadata(row['id'], track_data)
                return row['id']
        
        # 2. ISRC match
        if track_data.get('isrc'):
            query = "SELECT id FROM tracks WHERE isrc = $1 LIMIT 1"
            async with self.db.acquire() as conn:
                row = await conn.fetchrow(query, track_data['isrc'])
                if row:
                    logger.debug(f"Found ISRC match: track_id={row['id']}")
                    await self._update_track_metadata(row['id'], track_data)
                    return row['id']
        
        # 3. Fuzzy matching
        track_id = await self._fuzzy_match(normalized_title, normalized_artist, track_data)
        if track_id:
            return track_id
        
        # 4. MusicBrainz enrichment (optional)
        if self.enable_musicbrainz:
            mb_data = await self._query_musicbrainz(track_data['artist'], track_data['title'])
            if mb_data:
                track_data['musicbrainz_recording_id'] = mb_data.get('id')
                if not track_data.get('isrc') and mb_data.get('isrc'):
                    track_data['isrc'] = mb_data['isrc']
                    # Re-check ISRC match
                    query = "SELECT id FROM tracks WHERE isrc = $1 LIMIT 1"
                    async with self.db.acquire() as conn:
                        row = await conn.fetchrow(query, track_data['isrc'])
                        if row:
                            logger.info(f"Found track via MusicBrainz ISRC: track_id={row['id']}")
                            await self._update_track_metadata(row['id'], track_data)
                            return row['id']
        
        # 5. Create new track
        return await self._create_track(track_data, normalized_title, normalized_artist)
    
    async def _fuzzy_match(
        self, 
        normalized_title: str, 
        normalized_artist: str, 
        track_data: Dict[str, Any]
    ) -> Optional[int]:
        """Fuzzy matching for handling typos and variations"""
        # Search for candidates with similar artist name
        query = """
            SELECT id, normalized_title, normalized_artist 
            FROM tracks 
            WHERE normalized_artist ILIKE $1
            LIMIT 20
        """
        
        search_pattern = f"%{normalized_artist[:20]}%"
        
        async with self.db.acquire() as conn:
            candidates = await conn.fetch(query, search_pattern)
        
        for candidate in candidates:
            title_score = fuzz.ratio(normalized_title, candidate['normalized_title'])
            artist_score = fuzz.ratio(normalized_artist, candidate['normalized_artist'])
            
            # High threshold for fuzzy matching to avoid false positives
            if title_score >= 92 and artist_score >= 88:
                logger.info(
                    f"Fuzzy match found: track_id={candidate['id']} "
                    f"(title_score={title_score}, artist_score={artist_score})"
                )
                await self._update_track_metadata(candidate['id'], track_data)
                return candidate['id']
        
        return None
    
    async def _create_track(
        self, 
        track_data: Dict[str, Any], 
        normalized_title: str, 
        normalized_artist: str
    ) -> int:
        """Create new track in database"""
        query = """
            INSERT INTO tracks (
                title, artist, normalized_title, normalized_artist, 
                isrc, musicbrainz_recording_id, duration_ms, artwork_url
            )
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            RETURNING id
        """
        
        async with self.db.acquire() as conn:
            row = await conn.fetchrow(
                query,
                track_data['title'],
                track_data['artist'],
                normalized_title,
                normalized_artist,
                track_data.get('isrc'),
                track_data.get('musicbrainz_recording_id'),
                track_data.get('duration_ms'),
                track_data.get('artwork_url')
            )
        
        logger.info(f"Created new track: track_id={row['id']}, title='{track_data['title']}'")
        return row['id']
    
    async def _update_track_metadata(self, track_id: int, track_data: Dict[str, Any]):
        """Update track metadata if new data is better"""
        # Update artwork if missing
        if track_data.get('artwork_url'):
            query = """
                UPDATE tracks 
                SET artwork_url = COALESCE(artwork_url, $1),
                    isrc = COALESCE(isrc, $2),
                    duration_ms = COALESCE(duration_ms, $3)
                WHERE id = $4
            """
            async with self.db.acquire() as conn:
                await conn.execute(
                    query,
                    track_data['artwork_url'],
                    track_data.get('isrc'),
                    track_data.get('duration_ms'),
                    track_id
                )
    
    async def _query_musicbrainz(
        self, 
        artist: str, 
        title: str
    ) -> Optional[Dict[str, Any]]:
        """Query MusicBrainz for recording metadata"""
        try:
            params = {
                'query': f'artist:"{artist}" AND recording:"{title}"',
                'fmt': 'json',
                'limit': 1
            }
            
            response = await self.musicbrainz_client.get('/recording', params=params)
            
            if response.status_code == 429:  # Rate limited
                logger.warning("MusicBrainz rate limit hit")
                return None
            
            response.raise_for_status()
            data = response.json()
            
            recordings = data.get('recordings', [])
            if recordings:
                rec = recordings[0]
                isrcs = [isrc_data['isrc'] for isrc_data in rec.get('isrcs', [])]
                
                result = {
                    'id': rec.get('id'),
                    'isrc': isrcs[0] if isrcs else None,
                    'score': rec.get('score', 0)
                }
                
                logger.debug(f"MusicBrainz match: {result}")
                return result
                
        except Exception as e:
            logger.warning(f"MusicBrainz lookup failed: {e}")
        
        return None
    
    async def close(self):
        """Close HTTP client"""
        await self.musicbrainz_client.aclose()