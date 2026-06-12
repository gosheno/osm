ALTER TABLE addresses
    ADD COLUMN IF NOT EXISTS geocoding_query_used TEXT,
    ADD COLUMN IF NOT EXISTS geocoding_score NUMERIC(5, 2),
    ADD COLUMN IF NOT EXISTS cleaned_address TEXT,
    ADD COLUMN IF NOT EXISTS normalized_key TEXT,
    ADD COLUMN IF NOT EXISTS region_hint TEXT,
    ADD COLUMN IF NOT EXISTS settlement_hint TEXT,
    ADD COLUMN IF NOT EXISTS manual_reason TEXT,
    ADD COLUMN IF NOT EXISTS source_note TEXT,
    ADD COLUMN IF NOT EXISTS geocoding_context_label TEXT,
    ADD COLUMN IF NOT EXISTS geocoding_context_latitude DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS geocoding_context_longitude DOUBLE PRECISION,
    ADD COLUMN IF NOT EXISTS geocoding_context_radius_km NUMERIC(8, 2),
    ADD COLUMN IF NOT EXISTS geocoding_context_source VARCHAR(50);

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

DELETE FROM addresses
WHERE geocoding_provider = 'manual'
  AND (
      source_note ILIKE '%grid%'
      OR source_note ILIKE '%test%'
      OR manual_reason ILIKE '%grid%'
      OR manual_reason ILIKE '%test%'
  );
