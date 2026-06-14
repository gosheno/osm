CREATE TABLE IF NOT EXISTS known_pois (
    id BIGSERIAL PRIMARY KEY,

    osm_type TEXT NOT NULL,
    osm_id BIGINT NOT NULL,

    canonical_brand TEXT NOT NULL,
    detected_brand TEXT,
    name TEXT,
    operator TEXT,

    shop_type TEXT,
    amenity_type TEXT,

    original_address TEXT,
    normalized_address TEXT,

    country TEXT DEFAULT 'Russia',
    region TEXT,
    city TEXT,
    district TEXT,
    suburb TEXT,
    street TEXT,
    house_number TEXT,
    postcode TEXT,

    latitude DOUBLE PRECISION NOT NULL,
    longitude DOUBLE PRECISION NOT NULL,
    geom GEOMETRY(Point, 4326),

    phone TEXT,
    website TEXT,
    opening_hours TEXT,

    source TEXT NOT NULL DEFAULT 'osm_pbf',
    enrichment_source TEXT,
    raw_tags JSONB,

    confidence_score DOUBLE PRECISION DEFAULT 1.0,
    is_active BOOLEAN DEFAULT TRUE,
    is_duplicate BOOLEAN DEFAULT FALSE,
    duplicate_of_id BIGINT REFERENCES known_pois(id) ON DELETE SET NULL,

    imported_at TIMESTAMPTZ DEFAULT now(),
    updated_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE (osm_type, osm_id)
);

CREATE INDEX IF NOT EXISTS idx_known_pois_brand
    ON known_pois (canonical_brand);

CREATE INDEX IF NOT EXISTS idx_known_pois_normalized_address
    ON known_pois (normalized_address);

CREATE INDEX IF NOT EXISTS idx_known_pois_geom
    ON known_pois USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_known_pois_raw_tags
    ON known_pois USING GIN (raw_tags);

CREATE TABLE IF NOT EXISTS poi_brand_aliases (
    id BIGSERIAL PRIMARY KEY,
    canonical_brand TEXT NOT NULL,
    alias TEXT NOT NULL,
    normalized_alias TEXT NOT NULL,
    priority INT DEFAULT 100,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMPTZ DEFAULT now(),

    UNIQUE (canonical_brand, normalized_alias)
);

CREATE INDEX IF NOT EXISTS idx_poi_brand_aliases_normalized_alias
    ON poi_brand_aliases (normalized_alias);

CREATE TABLE IF NOT EXISTS poi_import_runs (
    id BIGSERIAL PRIMARY KEY,
    started_at TIMESTAMPTZ DEFAULT now(),
    finished_at TIMESTAMPTZ,
    status TEXT NOT NULL,

    source_file TEXT,
    region TEXT,

    total_objects_scanned BIGINT DEFAULT 0,
    total_candidates BIGINT DEFAULT 0,
    total_imported BIGINT DEFAULT 0,
    total_updated BIGINT DEFAULT 0,
    total_skipped BIGINT DEFAULT 0,
    total_duplicates BIGINT DEFAULT 0,
    total_errors BIGINT DEFAULT 0,

    error_message TEXT,
    report JSONB
);

DROP TRIGGER IF EXISTS trg_known_pois_updated_at ON known_pois;

CREATE TRIGGER trg_known_pois_updated_at
BEFORE UPDATE ON known_pois
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE INDEX IF NOT EXISTS idx_known_pois_normalized_address_trgm
ON known_pois USING GIN (normalized_address gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_known_pois_original_address_trgm
ON known_pois USING GIN (original_address gin_trgm_ops);

CREATE INDEX IF NOT EXISTS idx_known_pois_name_trgm
ON known_pois USING GIN (name gin_trgm_ops);
