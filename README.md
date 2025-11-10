# 🎵 Music Trend Panel

> **Aggregated music trends from Apple Music, YouTube & Spotify with intelligent deduplication, scoring, and buy links**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)

## 📋 Overview

Music Trend Panel is a production-ready MVP that aggregates trending music from multiple streaming platforms, normalizes track metadata, eliminates duplicates, and presents a unified view with intelligent scoring and purchase links.

### ✨ Key Features

- **Multi-Provider Integration**: Apple Music Charts, YouTube Most Popular, Spotify Category Playlists
- **Smart Deduplication**: Fuzzy matching, ISRC lookup, MusicBrainz enrichment
- **Intelligent Scoring**: Weighted ranking algorithm combining multiple signals
- **Where-to-Buy Links**: Deep links to Beatport, Traxsource, Bandcamp, Juno
- **RESTful API**: FastAPI with OpenAPI docs, pagination, filters
- **Modern Web UI**: Responsive Alpine.js interface with real-time updates
- **Export Formats**: CSV, M3U playlist, JSON
- **Docker Ready**: Complete docker-compose setup with PostgreSQL + Redis

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Web UI (Alpine.js)                 │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│            FastAPI REST API (OpenAPI)                │
├──────────────────────┬──────────────────────────────┤
│  Deduplication       │     Scoring Engine            │
│  Service             │     (Weighted Ranking)        │
└──────────────────────┴──────────────────────────────┘
           │                        │
┌──────────▼────────┐   ┌──────────▼────────┐
│  Provider Adapters │   │ PostgreSQL + Redis │
├───────────────────┤   └───────────────────┘
│ • Apple Music     │
│ • YouTube         │
│ • Spotify         │
│ • (Last.fm)       │
└───────────────────┘
```

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- API Keys:
  - [Apple Music API](https://developer.apple.com/documentation/applemusicapi/) (Team ID, Key ID, Private Key)
  - [YouTube Data API v3](https://developers.google.com/youtube/v3/getting-started) (API Key)
  - [Spotify Web API](https://developer.spotify.com/documentation/web-api/) (Client ID, Client Secret)

### Installation

1. **Clone the repository**
```bash
git clone https://github.com/djlyric/music-trend-panel.git
cd music-trend-panel
```

2. **Configure environment**
```bash
cp .env.example .env
# Edit .env and add your API credentials
```

3. **Start services**
```bash
docker-compose up -d
```

4. **Access the application**
- Web UI: http://localhost:8000
- API Docs: http://localhost:8000/docs
- Health Check: http://localhost:8000/health

5. **Fetch initial data**
```bash
curl -X POST "http://localhost:8000/api/refresh?region=DE&force=true"
```

## 📚 API Documentation

### Get Trends

```http
GET /api/trends?region=DE&genre=techhouse&limit=50
```

**Response:**
```json
{
  "results": [
    {
      "track": {
        "id": 1,
        "title": "Track Name",
        "artist": "Artist Name",
        "artwork_url": "https://..."
      },
      "combined_score": 95.5,
      "rank": 1,
      "sources": ["apple_music", "spotify", "youtube"],
      "trend_data": [...],
      "buy_links": [
        {
          "platform": "beatport",
          "url": "https://...",
          "verified": false
        }
      ]
    }
  ],
  "meta": {
    "region": "DE",
    "genre": "techhouse",
    "date": "2025-11-10",
    "count": 50
  }
}
```

### Refresh Data

```http
POST /api/refresh?region=DE&genre=techhouse&force=true
```

### Export

```http
GET /api/export?format=csv&region=DE&limit=100
```

Formats: `csv`, `m3u`, `json`

### Full API Documentation

Interactive API docs available at `/docs` (Swagger UI) and `/redoc` (ReDoc).

## 🔧 Configuration

### Environment Variables

See `.env.example` for full list. Key variables:

```bash
# Database
DATABASE_URL=postgresql://admin:password@localhost:5432/music_trends

# Apple Music
APPLE_TEAM_ID=YOUR_TEAM_ID
APPLE_KEY_ID=YOUR_KEY_ID
APPLE_PRIVATE_KEY="-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----"

# YouTube
YOUTUBE_API_KEY=YOUR_API_KEY

# Spotify
SPOTIFY_CLIENT_ID=YOUR_CLIENT_ID
SPOTIFY_CLIENT_SECRET=YOUR_CLIENT_SECRET

# Features
ENABLE_MUSICBRAINZ_ENRICHMENT=true
DEFAULT_REGION=DE
DEFAULT_GENRE=techhouse
```

### Supported Regions

ISO 3166-1 alpha-2 codes: `DE`, `AT`, `CH`, `US`, `GB`, `FR`, `ES`, `IT`, etc.

### Supported Genres

- `techhouse` - Tech House
- `techno` - Techno
- `house` - House
- `pop` - Pop
- `hiphop` - Hip Hop
- `rock` - Rock
- `electronic` - Electronic

## 🧪 Testing

```bash
# Run all tests
pytest

# With coverage
pytest --cov=app --cov-report=html

# Run specific test file
pytest tests/test_providers.py -v
```

## 📊 Scoring Algorithm

The combined score is calculated using a weighted average:

```
Score = Σ(provider_score × provider_weight × boost) / Σ(provider_weight)
```

**Provider Weights:**
- Apple Music: 1.0 (highest authority)
- Spotify: 0.85 (high engagement)
- YouTube: 0.65 (views as proxy)
- Last.fm: 0.40 (community signal)

**Provider-Specific Boosts:**
- YouTube: +1 per 1M views (max +25)
- Spotify: Blend with popularity score (0-100)
- Apple Music: +5 authority bonus

## 🔄 Deduplication Strategy

1. **Exact Match**: Normalized artist + title (lowercase, no special chars)
2. **ISRC Match**: International Standard Recording Code lookup
3. **Fuzzy Match**: Levenshtein distance (92% title, 88% artist threshold)
4. **MusicBrainz**: External enrichment for ISRC and metadata
5. **Create New**: If no match found

## 🐳 Docker Deployment

### Production Build

```bash
# Build optimized image
docker build -t music-trend-panel:latest .

# Run with environment file
docker run -d \
  --name music-trends \
  --env-file .env \
  -p 8000:8000 \
  music-trend-panel:latest
```

### Docker Compose (Recommended)

```bash
# Production mode
docker-compose -f docker-compose.yml up -d

# View logs
docker-compose logs -f api

# Stop services
docker-compose down
```

## 📁 Project Structure

```
music-trend-panel/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI application
│   ├── config.py            # Settings & configuration
│   ├── models.py            # Pydantic models
│   ├── providers/
│   │   ├── base.py          # Provider interface
│   │   ├── apple_music.py   # Apple Music adapter
│   │   ├── youtube.py       # YouTube adapter
│   │   └── spotify.py       # Spotify adapter
│   ├── services/
│   │   ├── deduplication.py # Track matching
│   │   └── scoring.py       # Ranking algorithm
│   └── templates/
│       └── index.html       # Web UI
├── migrations/
│   └── init.sql             # Database schema
├── tests/
│   ├── test_providers.py
│   ├── test_deduplication.py
│   └── test_api.py
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── .env.example
└── README.md
```

## ⚠️ Known Limitations

### API Compliance

- **Apple Music**: Requires paid Developer Program membership
- **YouTube**: Daily quota of 10,000 units (~200 requests)
- **Spotify**: Client Credentials limited to public data
- **Beatport**: Partner Program access required for official API

### Deduplication

- Fuzzy matching may have false positives for very similar titles
- MusicBrainz lookup can fail for obscure tracks
- ISRC data not always complete or accurate

### Scalability

- PostgreSQL schema optimized for <1M tracks
- For larger scale: implement partitioning and read replicas
- Redis caching reduces API calls but increases memory usage

## 🛣️ Roadmap

### Phase 2 (Weeks 3-4)
- [ ] Advanced MusicBrainz integration
- [ ] Beatport API official integration
- [ ] Automated buy-link verification
- [ ] Historical trend analysis

### Phase 3 (Weeks 5-6)
- [ ] Redis rate-limit management
- [ ] Background jobs (Celery)
- [ ] User authentication
- [ ] Admin dashboard

### Phase 4 (Future)
- [ ] Last.fm integration (feature flag)
- [ ] ML-based YouTube title parsing
- [ ] Personalized recommendations
- [ ] DJ tool exports (Rekordbox, Traktor)

## 🤝 Contributing

Contributions welcome! Please:

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

### Code Style

- Follow PEP 8
- Use `black` for formatting
- Add type hints
- Write docstrings
- Include tests

## 📄 License

MIT License - see [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- [Apple Music API](https://developer.apple.com/documentation/applemusicapi/)
- [YouTube Data API](https://developers.google.com/youtube/v3)
- [Spotify Web API](https://developer.spotify.com/documentation/web-api/)
- [MusicBrainz](https://musicbrainz.org/)
- [FastAPI](https://fastapi.tiangolo.com/)

## 📞 Support

For issues and questions:
- GitHub Issues: [Create an issue](https://github.com/djlyric/music-trend-panel/issues)
- Documentation: [API Docs](http://localhost:8000/docs)

---

**Built with ❤️ for music lovers and data enthusiasts**