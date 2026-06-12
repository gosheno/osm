ALTER TABLE addresses
    ADD COLUMN IF NOT EXISTS display_name TEXT,
    ADD COLUMN IF NOT EXISTS osm_type VARCHAR(20),
    ADD COLUMN IF NOT EXISTS osm_id BIGINT,
    ADD COLUMN IF NOT EXISTS place_id BIGINT,
    ADD COLUMN IF NOT EXISTS raw_response JSONB,
    ADD COLUMN IF NOT EXISTS candidates_json JSONB;

CREATE INDEX IF NOT EXISTS ix_addresses_place_id
    ON addresses (place_id);

CREATE INDEX IF NOT EXISTS ix_addresses_osm
    ON addresses (osm_type, osm_id);
