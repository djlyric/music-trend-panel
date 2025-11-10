"""Spotify Web API Provider"""
from .base import BaseProvider
from typing import List, Dict, Any, Optional
import base64
import logging

logger = logging.getLogger(__name__)


class SpotifyProvider(BaseProvider):
    """Spotify Category Playlists Provider (Trend Proxy)
    
    Documentation: https://developer.spotify.com/documentation/web-api/
    """
    
    def __init__(self, client_id: str, client_secret: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = None
        self.token_expiry = 0
        super().__init__("", "https://api.spotify.com/v1")
    
    async def _get_access_token(self) -> str:
        """Get access token using Client Credentials Flow"""
        import time
        
        # Check if we have a valid cached token
        if self.access_token and time.time() < self.token_expiry:
            return self.access_token
        
        # Get new token
        auth_str = f"{self.client_id}:{self.client_secret}"
        b64_auth = base64.b64encode(auth_str.encode()).decode()
        
        response = await self.client.post(
            "https://accounts.spotify.com/api/token",
            headers={
                'Authorization': f'Basic {b64_auth}',
                'Content-Type': 'application/x-www-form-urlencoded'
            },
            data={'grant_type': 'client_credentials'}
        )
        response.raise_for_status()
        
        token_data = response.json()
        self.access_token = token_data['access_token']
        self.token_expiry = time.time() + token_data.get('expires_in', 3600) - 60
        
        logger.info("Obtained new Spotify access token")
        return self.access_token
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json'
        }
    
    async def fetch_charts(
        self, 
        region: str = "DE", 
        genre: Optional[str] = "techhouse"
    ) -> List[Dict[str, Any]]:
        """Fetch tracks from Spotify category playlists
        
        Args:
            region: ISO 3166-1 alpha-2 country code
            genre: Genre/category name (techhouse, techno, pop, etc.)
            
        Returns:
            List of normalized track dictionaries
        """
        await self._get_access_token()
        
        # Map genre names to Spotify category IDs
        category_map = {
            'techhouse': 'edm_dance',
            'techno': 'edm_dance',
            'house': 'edm_dance',
            'pop': 'pop',
            'hiphop': 'hiphop',
            'rock': 'rock',
            'electronic': 'edm_dance'
        }
        
        category = category_map.get(genre.lower() if genre else '', 'toplists')
        
        try:
            # Get playlists for category
            params = {
                'country': region,
                'limit': 5
            }
            playlists_data = await self._make_request(
                f"/browse/categories/{category}/playlists",
                params
            )
            
            tracks = []
            playlists = playlists_data.get('playlists', {}).get('items', [])
            
            # Fetch tracks from top playlists
            for playlist in playlists[:3]:  # Limit to top 3 playlists
                playlist_id = playlist['id']
                
                track_params = {
                    'limit': 50,
                    'market': region
                }
                
                try:
                    playlist_tracks = await self._make_request(
                        f"/playlists/{playlist_id}/tracks",
                        track_params
                    )
                    
                    for idx, item in enumerate(playlist_tracks.get('items', []), len(tracks) + 1):
                        track_data = item.get('track')
                        if track_data and not track_data.get('is_local'):
                            try:
                                normalized = self.normalize_track(track_data)
                                normalized['rank'] = idx
                                tracks.append(normalized)
                            except Exception as e:
                                logger.warning(f"Failed to normalize track: {e}")
                                continue
                                
                except Exception as e:
                    logger.warning(f"Failed to fetch playlist {playlist_id}: {e}")
                    continue
            
            # Remove duplicates based on Spotify ID
            seen_ids = set()
            unique_tracks = []
            for track in tracks:
                spotify_id = track['metadata'].get('spotify_id')
                if spotify_id and spotify_id not in seen_ids:
                    seen_ids.add(spotify_id)
                    unique_tracks.append(track)
            
            # Limit to top 50 and re-rank
            unique_tracks = unique_tracks[:50]
            for idx, track in enumerate(unique_tracks, 1):
                track['rank'] = idx
            
            logger.info(f"Fetched {len(unique_tracks)} tracks from Spotify ({region}, {category})")
            return unique_tracks
            
        except Exception as e:
            logger.error(f"Spotify fetch failed: {e}")
            return []
    
    def normalize_track(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize Spotify track data"""
        # Combine artist names
        artists = raw_data.get('artists', [])
        artist_names = ', '.join([a['name'] for a in artists])
        
        # Get album artwork
        album = raw_data.get('album', {})
        images = album.get('images', [])
        artwork_url = images[0].get('url') if images else None
        
        # External IDs
        external_ids = raw_data.get('external_ids', {})
        isrc = external_ids.get('isrc')
        
        return {
            'title': raw_data.get('name', ''),
            'artist': artist_names,
            'isrc': isrc,
            'duration_ms': raw_data.get('duration_ms'),
            'artwork_url': artwork_url,
            'provider': 'spotify',
            'rank': 0,  # Set by caller
            'metadata': {
                'spotify_id': raw_data.get('id'),
                'popularity': raw_data.get('popularity', 0),
                'preview_url': raw_data.get('preview_url'),
                'url': raw_data.get('external_urls', {}).get('spotify'),
                'album': album.get('name'),
                'release_date': album.get('release_date'),
                'explicit': raw_data.get('explicit', False)
            }
        }