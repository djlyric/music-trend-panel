"""Apple Music API Provider"""
from .base import BaseProvider
from typing import List, Dict, Any, Optional
import jwt
import time
import logging

logger = logging.getLogger(__name__)


class AppleMusicProvider(BaseProvider):
    """Apple Music Catalog Charts Provider
    
    Documentation: https://developer.apple.com/documentation/applemusicapi/
    """
    
    def __init__(self, team_id: str, key_id: str, private_key: str):
        self.team_id = team_id
        self.key_id = key_id
        self.private_key = private_key
        self._token_cache = None
        self._token_expiry = 0
        super().__init__("", "https://api.music.apple.com/v1")
    
    def _generate_token(self) -> str:
        """Generate JWT Developer Token for Apple Music API"""
        # Check cache
        if self._token_cache and time.time() < self._token_expiry:
            return self._token_cache
        
        time_now = int(time.time())
        expiry = time_now + 15777000  # 6 months (max allowed)
        
        token = jwt.encode(
            {
                'iss': self.team_id,
                'iat': time_now,
                'exp': expiry
            },
            self.private_key,
            algorithm='ES256',
            headers={
                'alg': 'ES256',
                'kid': self.key_id
            }
        )
        
        self._token_cache = token
        self._token_expiry = expiry - 3600  # Refresh 1 hour before expiry
        
        logger.info("Generated new Apple Music API token")
        return token
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self._generate_token()}',
            'Accept': 'application/json'
        }
    
    async def fetch_charts(
        self, 
        storefront: str = "de", 
        genre: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch charts from Apple Music
        
        Args:
            storefront: Apple Music storefront ID (de, at, us, etc.)
            genre: Optional genre ID for filtering
            
        Returns:
            List of normalized track dictionaries
        """
        params = {
            'types': 'songs',
            'limit': 50
        }
        
        if genre:
            # Map genre names to Apple Music genre IDs
            genre_map = {
                'techhouse': '17',  # Electronic
                'techno': '17',
                'house': '17',
                'pop': '14',
                'hiphop': '18',
                'rock': '21'
            }
            genre_id = genre_map.get(genre.lower(), genre)
            params['genre'] = genre_id
        
        endpoint = f"/catalog/{storefront}/charts"
        
        try:
            data = await self._make_request(endpoint, params)
            
            tracks = []
            results = data.get('results', {})
            song_charts = results.get('songs', [])
            
            for chart in song_charts:
                chart_data = chart.get('data', [])
                for item in chart_data:
                    try:
                        normalized = self.normalize_track(item)
                        tracks.append(normalized)
                    except Exception as e:
                        logger.warning(f"Failed to normalize track: {e}")
                        continue
            
            logger.info(f"Fetched {len(tracks)} tracks from Apple Music ({storefront})")
            return tracks
            
        except Exception as e:
            logger.error(f"Apple Music fetch failed: {e}")
            return []
    
    def normalize_track(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Apple Music track data"""
        attributes = raw_data.get('attributes', {})
        artwork = attributes.get('artwork', {})
        
        # Replace template variables in artwork URL
        artwork_url = artwork.get('url', '')
        if artwork_url:
            artwork_url = artwork_url.replace('{w}', '400').replace('{h}', '400')
        
        # Get preview URL
        previews = attributes.get('previews', [])
        preview_url = previews[0].get('url') if previews else None
        
        return {
            'title': attributes.get('name', ''),
            'artist': attributes.get('artistName', ''),
            'isrc': attributes.get('isrc'),
            'duration_ms': attributes.get('durationInMillis'),
            'artwork_url': artwork_url or None,
            'provider': 'apple_music',
            'rank': raw_data.get('attributes', {}).get('chartPosition', 0),
            'metadata': {
                'apple_music_id': raw_data.get('id'),
                'album': attributes.get('albumName'),
                'preview_url': preview_url,
                'release_date': attributes.get('releaseDate'),
                'genre_names': attributes.get('genreNames', []),
                'url': attributes.get('url')
            }
        }