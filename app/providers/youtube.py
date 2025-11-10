"""YouTube Data API Provider"""
from .base import BaseProvider
from typing import List, Dict, Any, Optional
import isodate
import re
import logging

logger = logging.getLogger(__name__)


class YouTubeProvider(BaseProvider):
    """YouTube Most Popular Videos Provider (Music Category)
    
    Documentation: https://developers.google.com/youtube/v3/docs/videos/list
    """
    
    def __init__(self, api_key: str):
        super().__init__(api_key, "https://www.googleapis.com/youtube/v3")
    
    def _get_headers(self) -> Dict[str, str]:
        return {
            'Accept': 'application/json'
        }
    
    async def fetch_charts(
        self, 
        region: str = "DE", 
        genre: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch most popular music videos from YouTube
        
        Args:
            region: ISO 3166-1 alpha-2 country code
            genre: Ignored (YouTube doesn't support genre filtering for charts)
            
        Returns:
            List of normalized track dictionaries
        """
        params = {
            'part': 'snippet,contentDetails,statistics',
            'chart': 'mostPopular',
            'videoCategoryId': '10',  # Music category
            'regionCode': region,
            'maxResults': 50,
            'key': self.api_key
        }
        
        try:
            data = await self._make_request("/videos", params)
            
            tracks = []
            items = data.get('items', [])
            
            for idx, item in enumerate(items, 1):
                try:
                    normalized = self.normalize_track(item)
                    if normalized:  # Filter out non-music content
                        normalized['rank'] = idx
                        tracks.append(normalized)
                except Exception as e:
                    logger.warning(f"Failed to normalize YouTube video: {e}")
                    continue
            
            logger.info(f"Fetched {len(tracks)} tracks from YouTube ({region})")
            return tracks
            
        except Exception as e:
            logger.error(f"YouTube fetch failed: {e}")
            return []
    
    def normalize_track(self, raw_data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Normalize YouTube video data
        
        Attempts to parse artist and title from video title.
        Returns None if parsing fails (likely not a music video).
        """
        snippet = raw_data.get('snippet', {})
        title = snippet.get('title', '')
        
        # Parse artist and track title
        artist, track_title = self._parse_youtube_title(title)
        
        if not artist or not track_title:
            logger.debug(f"Skipping non-music video: {title}")
            return None
        
        stats = raw_data.get('statistics', {})
        content_details = raw_data.get('contentDetails', {})
        
        # Parse ISO 8601 duration
        duration_ms = self._parse_duration(content_details.get('duration', 'PT0S'))
        
        # Get thumbnail
        thumbnails = snippet.get('thumbnails', {})
        artwork_url = (
            thumbnails.get('maxres', {}).get('url') or
            thumbnails.get('high', {}).get('url') or
            thumbnails.get('medium', {}).get('url')
        )
        
        video_id = raw_data.get('id')
        
        return {
            'title': track_title,
            'artist': artist,
            'isrc': None,  # YouTube doesn't provide ISRC
            'duration_ms': duration_ms,
            'artwork_url': artwork_url,
            'provider': 'youtube',
            'rank': 0,  # Set by caller
            'metadata': {
                'video_id': video_id,
                'view_count': int(stats.get('viewCount', 0)),
                'like_count': int(stats.get('likeCount', 0)),
                'comment_count': int(stats.get('commentCount', 0)),
                'url': f"https://www.youtube.com/watch?v={video_id}",
                'published_at': snippet.get('publishedAt'),
                'channel': snippet.get('channelTitle')
            }
        }
    
    def _parse_youtube_title(self, title: str) -> tuple[str, str]:
        """Extract artist and track title from YouTube video title
        
        Common patterns:
        - Artist - Track
        - Artist – Track (em dash)
        - Artist | Track
        - Artist || Track
        - Artist "Track"
        """
        # Try common separators
        separators = [' - ', ' – ', ' — ', ' | ', ' || ', ': ']
        
        for sep in separators:
            if sep in title:
                parts = title.split(sep, 1)
                artist = parts[0].strip()
                track = parts[1].strip()
                
                # Clean up common suffixes
                track = re.sub(r'\s*\(Official.*?\)\s*', '', track, flags=re.IGNORECASE)
                track = re.sub(r'\s*\[Official.*?\]\s*', '', track, flags=re.IGNORECASE)
                track = re.sub(r'\s*\(Music Video\)\s*', '', track, flags=re.IGNORECASE)
                track = re.sub(r'\s*\[HD\]\s*', '', track, flags=re.IGNORECASE)
                
                # Remove quotes
                track = track.strip('"\'')
                
                if artist and track:
                    return artist, track
        
        # No separator found - likely not a music video
        return "", title
    
    def _parse_duration(self, iso_duration: str) -> int:
        """Convert ISO 8601 duration to milliseconds"""
        try:
            duration = isodate.parse_duration(iso_duration)
            return int(duration.total_seconds() * 1000)
        except Exception as e:
            logger.warning(f"Failed to parse duration '{iso_duration}': {e}")
            return 0