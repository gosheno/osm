CREATE EXTENSION IF NOT EXISTS postgis;

CREATE TABLE IF NOT EXISTS addresses (
    id BIGSERIAL PRIMARY KEY,
    original_address TEXT NOT NULL,
    normalized_address TEXT NOT NULL,
    latitude DOUBLE PRECISION,
    longitude DOUBLE PRECISION,
    geom geometry(Point, 4326),
    geocoding_status VARCHAR(20) NOT NULL DEFAULT 'pending',
    geocoding_provider VARCHAR(50),
    confidence_score NUMERIC(5, 2),
    geocoding_query_used TEXT,
    geocoding_score NUMERIC(5, 2),
    display_name TEXT,
    osm_type VARCHAR(20),
    osm_id BIGINT,
    place_id BIGINT,
    raw_response JSONB,
    candidates_json JSONB,
    cleaned_address TEXT,
    normalized_key TEXT,
    region_hint TEXT,
    settlement_hint TEXT,
    manual_reason TEXT,
    source_note TEXT,
    geocoding_context_label TEXT,
    geocoding_context_latitude DOUBLE PRECISION,
    geocoding_context_longitude DOUBLE PRECISION,
    geocoding_context_radius_km NUMERIC(8, 2),
    geocoding_context_source VARCHAR(50),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_used_at TIMESTAMPTZ,

    CONSTRAINT chk_addresses_geocoding_status
        CHECK (geocoding_status IN ('pending', 'found', 'not_found', 'ambiguous', 'manual')),

    CONSTRAINT chk_addresses_latitude
        CHECK (latitude IS NULL OR latitude BETWEEN -90 AND 90),

    CONSTRAINT chk_addresses_longitude
        CHECK (longitude IS NULL OR longitude BETWEEN -180 AND 180)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_addresses_normalized_address
    ON addresses (normalized_address);

CREATE INDEX IF NOT EXISTS ix_addresses_geom
    ON addresses USING GIST (geom);

CREATE INDEX IF NOT EXISTS ix_addresses_geocoding_status
    ON addresses (geocoding_status);

CREATE TABLE IF NOT EXISTS geocoding_attempts (
    id BIGSERIAL PRIMARY KEY,
    address_id BIGINT REFERENCES addresses(id) ON DELETE CASCADE,
    original_address TEXT,
    normalized_address TEXT,
    query TEXT NOT NULL,
    provider VARCHAR(50),
    status VARCHAR(30) NOT NULL,
    candidates_count INTEGER NOT NULL DEFAULT 0,
    score NUMERIC(5, 2),
    selected BOOLEAN NOT NULL DEFAULT false,
    viewbox TEXT,
    bounded BOOLEAN DEFAULT false,
    distance_to_context_m NUMERIC(12, 2),
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_geocoding_attempts_address_id
    ON geocoding_attempts (address_id);

CREATE INDEX IF NOT EXISTS ix_geocoding_attempts_created_at
    ON geocoding_attempts (created_at);

CREATE TABLE IF NOT EXISTS route_jobs (
    id BIGSERIAL PRIMARY KEY,
    name TEXT,
    start_address_id BIGINT REFERENCES addresses(id),
    end_address_id BIGINT REFERENCES addresses(id),
    status VARCHAR(30) NOT NULL DEFAULT 'created',
    total_distance_m DOUBLE PRECISION,
    total_duration_s DOUBLE PRECISION,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,

    CONSTRAINT chk_route_jobs_status
        CHECK (status IN ('created', 'geocoding', 'optimizing', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_route_jobs_status
    ON route_jobs (status);

CREATE INDEX IF NOT EXISTS ix_route_jobs_created_at
    ON route_jobs (created_at);

CREATE TABLE IF NOT EXISTS route_points (
    id BIGSERIAL PRIMARY KEY,
    route_job_id BIGINT NOT NULL REFERENCES route_jobs(id) ON DELETE CASCADE,
    address_id BIGINT NOT NULL REFERENCES addresses(id),
    original_order INTEGER,
    optimized_order INTEGER,
    batch_number INTEGER,
    is_start_point BOOLEAN NOT NULL DEFAULT false,
    is_end_point BOOLEAN NOT NULL DEFAULT false,
    distance_from_previous_m DOUBLE PRECISION,
    duration_from_previous_s DOUBLE PRECISION,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_route_points_not_both_start_end
        CHECK (NOT (is_start_point = true AND is_end_point = true))
);

CREATE INDEX IF NOT EXISTS ix_route_points_route_job_id
    ON route_points (route_job_id);

CREATE INDEX IF NOT EXISTS ix_route_points_address_id
    ON route_points (address_id);

CREATE INDEX IF NOT EXISTS ix_route_points_optimized_order
    ON route_points (route_job_id, optimized_order);

CREATE INDEX IF NOT EXISTS ix_route_points_batch_number
    ON route_points (route_job_id, batch_number);

CREATE TABLE IF NOT EXISTS route_batches (
    id BIGSERIAL PRIMARY KEY,
    route_job_id BIGINT NOT NULL REFERENCES route_jobs(id) ON DELETE CASCADE,
    batch_number INTEGER NOT NULL,
    points_count INTEGER NOT NULL,
    distance_m DOUBLE PRECISION,
    duration_s DOUBLE PRECISION,
    yandex_maps_url TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_route_batches_job_batch
        UNIQUE (route_job_id, batch_number),

    CONSTRAINT chk_route_batches_points_count
        CHECK (points_count > 0)
);

CREATE INDEX IF NOT EXISTS ix_route_batches_route_job_id
    ON route_batches (route_job_id);

CREATE OR REPLACE FUNCTION set_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_addresses_updated_at ON addresses;

CREATE TRIGGER trg_addresses_updated_at
BEFORE UPDATE ON addresses
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
