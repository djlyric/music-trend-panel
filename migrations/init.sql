-- Music Trend Panel Database Schema
-- Version: 1.0.0
-- Created: 2025-11-10

-- Enable extensions
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Tracks table (normalized music metadata)
CREATE TABLE IF NOT EXISTS tracks (
    id SERIAL PRIMARY KEY,
    title VARCHAR(500) NOT NULL,
    artist VARCHAR(500) NOT NULL,
    normalized_title VARCHAR(500),
    normalized_artist VARCHAR(500),
    isrc VARCHAR(12),
    musicbrainz_recording_id UUID,
    duration_ms INTEGER,
    artwork_url TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    updated_at TIMESTAMP DEFAULT NOW()
);

-- Trend entries (provider-specific chart data)
CREATE TABLE IF NOT EXISTS trend_entries (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    provider VARCHAR(50) NOT NULL CHECK (provider IN ('apple_music', 'youtube', 'spotify', 'lastfm')),
    rank INTEGER CHECK (rank > 0),
    score DECIMAL(10,2) NOT NULL,
    region VARCHAR(10) NOT NULL,
    genre VARCHAR(100),
    chart_date DATE NOT NULL DEFAULT CURRENT_DATE,
    metadata JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_trend_entry UNIQUE(track_id, provider, region, genre, chart_date)
);

-- Buy links (where-to-buy sources)
CREATE TABLE IF NOT EXISTS buy_links (
    id SERIAL PRIMARY KEY,
    track_id INTEGER NOT NULL REFERENCES tracks(id) ON DELETE CASCADE,
    platform VARCHAR(50) NOT NULL CHECK (platform IN ('beatport', 'traxsource', 'bandcamp', 'juno', 'apple_music', 'spotify')),
    url TEXT NOT NULL,
    verified BOOLEAN DEFAULT FALSE,
    last_checked TIMESTAMP,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT unique_buy_link UNIQUE(track_id, platform)
);

-- Indices for performance optimization

-- Tracks indices
CREATE INDEX idx_tracks_normalized ON tracks(normalized_artist, normalized_title);
CREATE INDEX idx_tracks_isrc ON tracks(isrc) WHERE isrc IS NOT NULL;
CREATE INDEX idx_tracks_musicbrainz ON tracks(musicbrainz_recording_id) WHERE musicbrainz_recording_id IS NOT NULL;
CREATE INDEX idx_tracks_created ON tracks(created_at DESC);

-- Trend entries indices
CREATE INDEX idx_trend_entries_lookup ON trend_entries(region, genre, chart_date, score DESC);
CREATE INDEX idx_trend_entries_track ON trend_entries(track_id);
CREATE INDEX idx_trend_entries_provider ON trend_entries(provider, chart_date);
CREATE INDEX idx_trend_entries_date ON trend_entries(chart_date DESC);
CREATE INDEX idx_trend_entries_metadata ON trend_entries USING GIN (metadata);

-- Buy links indices
CREATE INDEX idx_buy_links_track ON buy_links(track_id);
CREATE INDEX idx_buy_links_platform ON buy_links(platform);

-- Trigger to update updated_at timestamp
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE TRIGGER update_tracks_updated_at BEFORE UPDATE ON tracks
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

-- Views for common queries

-- Aggregated trends view
CREATE OR REPLACE VIEW v_aggregated_trends AS
SELECT 
    t.id as track_id,
    t.title,
    t.artist,
    t.artwork_url,
    te.region,
    te.genre,
    te.chart_date,
    AVG(te.score) as avg_score,
    COUNT(DISTINCT te.provider) as source_count,
    ARRAY_AGG(DISTINCT te.provider) as sources,
    MIN(te.rank) as best_rank
FROM tracks t
JOIN trend_entries te ON t.id = te.track_id
GROUP BY t.id, t.title, t.artist, t.artwork_url, te.region, te.genre, te.chart_date;

-- Comments
COMMENT ON TABLE tracks IS 'Normalized music track metadata from all providers';
COMMENT ON TABLE trend_entries IS 'Provider-specific chart positions and scores';
COMMENT ON TABLE buy_links IS 'Purchase and streaming links for tracks';
COMMENT ON COLUMN tracks.normalized_title IS 'Lowercase title without special characters for matching';
COMMENT ON COLUMN tracks.normalized_artist IS 'Lowercase artist without special characters for matching';
COMMENT ON COLUMN tracks.isrc IS 'International Standard Recording Code for deduplication';
COMMENT ON COLUMN trend_entries.metadata IS 'Provider-specific data (view counts, popularity, etc.)';