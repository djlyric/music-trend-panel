"""Music Provider Adapters"""
from .base import BaseProvider
from .apple_music import AppleMusicProvider
from .youtube import YouTubeProvider
from .spotify import SpotifyProvider

__all__ = [
    "BaseProvider",
    "AppleMusicProvider",
    "YouTubeProvider",
    "SpotifyProvider",
]