"""Base Provider Interface"""
from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential
import logging

logger = logging.getLogger(__name__)


class BaseProvider(ABC):
    """Abstract base class for music data providers"""
    
    def __init__(self, api_key: str, base_url: str):
        self.api_key = api_key
        self.base_url = base_url
        self.client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10)
        )
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10)
    )
    async def _make_request(
        self, 
        endpoint: str, 
        params: Optional[Dict[str, Any]] = None,
        method: str = "GET"
    ) -> Dict[str, Any]:
        """Make HTTP request with retry logic and backoff"""
        try:
            url = f"{self.base_url}{endpoint}"
            headers = self._get_headers()
            
            logger.debug(f"Making {method} request to {url}")
            
            if method == "GET":
                response = await self.client.get(url, params=params, headers=headers)
            elif method == "POST":
                response = await self.client.post(url, json=params, headers=headers)
            else:
                raise ValueError(f"Unsupported method: {method}")
            
            response.raise_for_status()
            return response.json()
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error {e.response.status_code}: {e.response.text}")
            raise
        except Exception as e:
            logger.error(f"Request failed: {str(e)}")
            raise
    
    @abstractmethod
    def _get_headers(self) -> Dict[str, str]:
        """Get provider-specific HTTP headers"""
        pass
    
    @abstractmethod
    async def fetch_charts(
        self, 
        region: str, 
        genre: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch charts from provider
        
        Args:
            region: ISO 3166-1 alpha-2 country code
            genre: Optional genre filter
            
        Returns:
            List of normalized track dictionaries
        """
        pass
    
    @abstractmethod
    def normalize_track(self, raw_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize provider-specific track data to common format
        
        Args:
            raw_data: Raw track data from provider API
            
        Returns:
            Normalized track dictionary with standard fields:
            - title: str
            - artist: str
            - isrc: Optional[str]
            - duration_ms: Optional[int]
            - artwork_url: Optional[str]
            - provider: str
            - rank: Optional[int]
            - metadata: Dict[str, Any]
        """
        pass
    
    async def close(self):
        """Close HTTP client connection"""
        await self.client.aclose()
    
    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}>"