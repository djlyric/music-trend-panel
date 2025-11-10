"""Trend Scoring and Ranking Service"""
from typing import List, Dict, Any
from datetime import date, timedelta
import logging

logger = logging.getLogger(__name__)


class ScoringService:
    """Service for calculating combined scores and rankings"""
    
    # Provider weights (configurable)
    PROVIDER_WEIGHTS = {
        'apple_music': 1.0,    # Highest authority
        'spotify': 0.85,       # High engagement signals
        'youtube': 0.65,       # Views as popularity proxy
        'lastfm': 0.40         # Community signal
    }
    
    def calculate_combined_score(self, trend_entries: List[Dict[str, Any]]) -> float:
        """Calculate combined score from multiple providers
        
        Formula: Σ(normalized_rank_score × provider_weight × boost) / num_providers
        
        Args:
            trend_entries: List of trend entry dicts with provider, rank, metadata
            
        Returns:
            Combined score (0-100 scale, higher is better)
        """
        if not trend_entries:
            return 0.0
        
        total_weighted_score = 0.0
        total_weight = 0.0
        
        for entry in trend_entries:
            provider = entry.get('provider')
            provider_weight = self.PROVIDER_WEIGHTS.get(provider, 0.5)
            
            # Base score from rank (inverse: lower rank = higher score)
            rank = entry.get('rank', 50)
            if rank:
                # Normalize to 0-100 (rank 1 = 100, rank 100+ = 0)
                base_score = max(0, 100 - rank)
            else:
                base_score = 50  # Default for rankless sources
            
            # Provider-specific adjustments
            boost = 0
            metadata = entry.get('metadata', {})
            
            if provider == 'youtube':
                # Boost based on view count
                view_count = metadata.get('view_count', 0)
                if view_count > 0:
                    # +1 per million views, max +25
                    boost = min(25, view_count / 1_000_000)
            
            elif provider == 'spotify':
                # Use Spotify's popularity score (0-100)
                popularity = metadata.get('popularity', 0)
                if popularity > 0:
                    # Blend with rank score
                    base_score = (base_score + popularity) / 2
            
            elif provider == 'apple_music':
                # Apple Music charts are authoritative, slight boost
                boost = 5
            
            final_score = (base_score + boost) * provider_weight
            total_weighted_score += final_score
            total_weight += provider_weight
        
        # Average weighted score
        if total_weight > 0:
            combined_score = total_weighted_score / total_weight
        else:
            combined_score = 0.0
        
        return round(min(100, combined_score), 2)
    
    def calculate_velocity(
        self, 
        track_id: int, 
        current_score: float, 
        historical_scores: List[tuple[date, float]]
    ) -> float:
        """Calculate trend velocity (rate of change)
        
        Args:
            track_id: Track ID
            current_score: Current combined score
            historical_scores: List of (date, score) tuples
            
        Returns:
            Velocity score (positive = rising, negative = falling)
        """
        if len(historical_scores) < 2:
            return 0.0
        
        # Get scores from last 7 days
        cutoff_date = date.today() - timedelta(days=7)
        recent_scores = [
            (d, s) for d, s in historical_scores 
            if d >= cutoff_date
        ]
        
        if len(recent_scores) < 2:
            return 0.0
        
        # Sort by date
        recent_scores.sort(key=lambda x: x[0])
        
        # Calculate average change
        oldest_score = recent_scores[0][1]
        velocity = current_score - oldest_score
        
        return round(velocity, 2)
    
    def rank_tracks(self, tracks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Rank tracks by combined score
        
        Args:
            tracks: List of track dicts with trend_data
            
        Returns:
            Sorted and ranked list of tracks
        """
        # Calculate combined scores
        for track in tracks:
            trend_entries = track.get('trend_data', [])
            track['combined_score'] = self.calculate_combined_score(trend_entries)
        
        # Sort by score (descending)
        sorted_tracks = sorted(
            tracks, 
            key=lambda x: x['combined_score'], 
            reverse=True
        )
        
        # Assign ranks
        for idx, track in enumerate(sorted_tracks, 1):
            track['rank'] = idx
        
        return sorted_tracks