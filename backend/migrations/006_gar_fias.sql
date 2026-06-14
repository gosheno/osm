CREATE EXTENSION IF NOT EXISTS pg_trgm;

CREATE TABLE IF NOT EXISTS gar_regions (
    id BIGSERIAL PRIMARY KEY,
    gar_id TEXT,
    region_code TEXT NOT NULL,
    name TEXT NOT NULL,
    short_name TEXT,
    is_actual BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_gar_regions_region_code UNIQUE (region_code)
);

CREATE TABLE IF NOT EXISTS gar_address_objects (
    id BIGSERIAL PRIMARY KEY,
    gar_id TEXT,
    object_id BIGINT NOT NULL,
    parent_object_id BIGINT,
    object_level INTEGER,
    name TEXT NOT NULL,
    type_name TEXT,
    full_name TEXT NOT NULL,
    region_code TEXT,
    is_actual BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    path TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_gar_address_objects_object_id UNIQUE (object_id)
);

CREATE INDEX IF NOT EXISTS ix_gar_address_objects_region_level
    ON gar_address_objects (region_code, object_level);

CREATE INDEX IF NOT EXISTS ix_gar_address_objects_parent
    ON gar_address_objects (parent_object_id);

CREATE INDEX IF NOT EXISTS ix_gar_address_objects_name_trgm
    ON gar_address_objects USING GIN (lower(name) gin_trgm_ops);

CREATE INDEX IF NOT EXISTS ix_gar_address_objects_full_name_trgm
    ON gar_address_objects USING GIN (lower(full_name) gin_trgm_ops);

CREATE TABLE IF NOT EXISTS gar_houses (
    id BIGSERIAL PRIMARY KEY,
    gar_id TEXT,
    object_id BIGINT,
    house_id BIGINT NOT NULL,
    parent_object_id BIGINT,
    house_number TEXT,
    building_number TEXT,
    structure_number TEXT,
    house_type TEXT,
    building_type TEXT,
    structure_type TEXT,
    postcode TEXT,
    region_code TEXT,
    is_actual BOOLEAN NOT NULL DEFAULT TRUE,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT ux_gar_houses_house_id UNIQUE (house_id)
);

CREATE UNIQUE INDEX IF NOT EXISTS ux_gar_houses_object_id
    ON gar_houses (object_id)
    WHERE object_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS ix_gar_houses_parent
    ON gar_houses (parent_object_id);

CREATE INDEX IF NOT EXISTS ix_gar_houses_region
    ON gar_houses (region_code);

CREATE INDEX IF NOT EXISTS ix_gar_houses_house_number_trgm
    ON gar_houses USING GIN (lower(coalesce(house_number, '')) gin_trgm_ops);

CREATE TABLE IF NOT EXISTS gar_import_runs (
    id BIGSERIAL PRIMARY KEY,
    region TEXT NOT NULL,
    source_path TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    address_objects_imported BIGINT NOT NULL DEFAULT 0,
    houses_imported BIGINT NOT NULL DEFAULT 0,
    updated BIGINT NOT NULL DEFAULT 0,
    skipped BIGINT NOT NULL DEFAULT 0,
    errors BIGINT NOT NULL DEFAULT 0,
    error_message TEXT,
    report JSONB,
    started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at TIMESTAMPTZ,

    CONSTRAINT chk_gar_import_runs_status
        CHECK (status IN ('pending', 'running', 'completed', 'failed'))
);

CREATE INDEX IF NOT EXISTS ix_gar_import_runs_status
    ON gar_import_runs (status);

CREATE TABLE IF NOT EXISTS addresses_raw (
    id BIGSERIAL PRIMARY KEY,
    source_file_id BIGINT,
    shop_name TEXT,
    raw_address TEXT NOT NULL,
    raw_row_number INTEGER,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_addresses_raw_source_file_id
    ON addresses_raw (source_file_id);

CREATE TABLE IF NOT EXISTS addresses_normalized (
    id BIGSERIAL PRIMARY KEY,
    raw_address_id BIGINT REFERENCES addresses_raw(id) ON DELETE CASCADE,
    normalized_full_address TEXT,
    region TEXT,
    city TEXT,
    settlement TEXT,
    district TEXT,
    street TEXT,
    house TEXT,
    building TEXT,
    structure TEXT,
    postcode TEXT,
    gar_object_id BIGINT REFERENCES gar_address_objects(id) ON DELETE SET NULL,
    gar_house_id BIGINT REFERENCES gar_houses(id) ON DELETE SET NULL,
    fias_id TEXT,
    normalization_status TEXT NOT NULL,
    normalization_confidence NUMERIC(4, 3),
    normalization_comment TEXT,
    variants JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_addresses_normalized_status
        CHECK (normalization_status IN (
            'exact_match',
            'partial_match',
            'ambiguous',
            'not_found',
            'manual_review'
        ))
);

CREATE INDEX IF NOT EXISTS ix_addresses_normalized_raw_address_id
    ON addresses_normalized (raw_address_id);

CREATE INDEX IF NOT EXISTS ix_addresses_normalized_status
    ON addresses_normalized (normalization_status);

CREATE INDEX IF NOT EXISTS ix_addresses_normalized_full_address_trgm
    ON addresses_normalized USING GIN (lower(coalesce(normalized_full_address, '')) gin_trgm_ops);

CREATE TABLE IF NOT EXISTS geocoding_results (
    id BIGSERIAL PRIMARY KEY,
    normalized_address_id BIGINT REFERENCES addresses_normalized(id) ON DELETE CASCADE,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    geom GEOMETRY(Point, 4326),
    geocoder TEXT,
    matched_osm_type TEXT,
    matched_osm_id BIGINT,
    matched_place_id BIGINT,
    precision TEXT,
    confidence NUMERIC(5, 2),
    distance_to_road_m NUMERIC(12, 2),
    snap_status TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_geocoding_results_precision
        CHECK (precision IS NULL OR precision IN (
            'house',
            'building',
            'street',
            'settlement',
            'city',
            'region',
            'unknown'
        )),

    CONSTRAINT chk_geocoding_results_snap_status
        CHECK (snap_status IS NULL OR snap_status IN (
            'ok',
            'low_precision',
            'outside_region',
            'too_far_from_road',
            'duplicate_coordinates',
            'geocoding_failed',
            'manual_review'
        )),

    CONSTRAINT chk_geocoding_results_latitude
        CHECK (lat IS NULL OR lat BETWEEN -90 AND 90),

    CONSTRAINT chk_geocoding_results_longitude
        CHECK (lon IS NULL OR lon BETWEEN -180 AND 180)
);

CREATE INDEX IF NOT EXISTS ix_geocoding_results_normalized_address_id
    ON geocoding_results (normalized_address_id);

CREATE INDEX IF NOT EXISTS ix_geocoding_results_geom
    ON geocoding_results USING GIST (geom);

CREATE TABLE IF NOT EXISTS address_processing_logs (
    id BIGSERIAL PRIMARY KEY,
    raw_address_id BIGINT REFERENCES addresses_raw(id) ON DELETE CASCADE,
    step TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    payload JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS ix_address_processing_logs_raw_address_id
    ON address_processing_logs (raw_address_id);

CREATE TABLE IF NOT EXISTS gar_osm_links (
    id BIGSERIAL PRIMARY KEY,
    gar_house_id BIGINT NOT NULL REFERENCES gar_houses(id) ON DELETE CASCADE,
    osm_type TEXT,
    osm_id BIGINT,
    lat DOUBLE PRECISION,
    lon DOUBLE PRECISION,
    geom GEOMETRY(Point, 4326),
    match_type TEXT NOT NULL,
    confidence NUMERIC(5, 2),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_gar_osm_links_match_type
        CHECK (match_type IN (
            'exact_addr_match',
            'street_house_match',
            'nearest_building_match',
            'manual_match'
        )),

    CONSTRAINT ux_gar_osm_links_house_osm UNIQUE (gar_house_id, osm_type, osm_id)
);

CREATE INDEX IF NOT EXISTS ix_gar_osm_links_geom
    ON gar_osm_links USING GIST (geom);

DROP TRIGGER IF EXISTS trg_gar_regions_updated_at ON gar_regions;
CREATE TRIGGER trg_gar_regions_updated_at
BEFORE UPDATE ON gar_regions
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_gar_address_objects_updated_at ON gar_address_objects;
CREATE TRIGGER trg_gar_address_objects_updated_at
BEFORE UPDATE ON gar_address_objects
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_gar_houses_updated_at ON gar_houses;
CREATE TRIGGER trg_gar_houses_updated_at
BEFORE UPDATE ON gar_houses
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_addresses_normalized_updated_at ON addresses_normalized;
CREATE TRIGGER trg_addresses_normalized_updated_at
BEFORE UPDATE ON addresses_normalized
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_geocoding_results_updated_at ON geocoding_results;
CREATE TRIGGER trg_geocoding_results_updated_at
BEFORE UPDATE ON geocoding_results
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_gar_osm_links_updated_at ON gar_osm_links;
CREATE TRIGGER trg_gar_osm_links_updated_at
BEFORE UPDATE ON gar_osm_links
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
