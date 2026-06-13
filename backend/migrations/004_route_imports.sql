CREATE TABLE IF NOT EXISTS route_imports (
    id BIGSERIAL PRIMARY KEY,
    status VARCHAR(30) NOT NULL DEFAULT 'uploaded',
    source_type VARCHAR(30) NOT NULL DEFAULT 'route_sheet',
    ocr_engine VARCHAR(50),
    raw_text TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error_message TEXT,

    CONSTRAINT chk_route_imports_status
        CHECK (status IN ('uploaded', 'processing', 'completed', 'failed', 'confirmed'))
);

CREATE INDEX IF NOT EXISTS ix_route_imports_status
    ON route_imports (status);

CREATE INDEX IF NOT EXISTS ix_route_imports_created_at
    ON route_imports (created_at);

CREATE TABLE IF NOT EXISTS route_import_images (
    id BIGSERIAL PRIMARY KEY,
    import_id BIGINT NOT NULL REFERENCES route_imports(id) ON DELETE CASCADE,
    file_path TEXT NOT NULL,
    original_filename TEXT NOT NULL,
    image_order INTEGER NOT NULL,
    preprocessed_file_path TEXT,
    ocr_status VARCHAR(30) NOT NULL DEFAULT 'uploaded',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    error_message TEXT
);

CREATE INDEX IF NOT EXISTS ix_route_import_images_import_id
    ON route_import_images (import_id);

CREATE TABLE IF NOT EXISTS route_import_items (
    id BIGSERIAL PRIMARY KEY,
    import_id BIGINT NOT NULL REFERENCES route_imports(id) ON DELETE CASCADE,
    source_image_id BIGINT REFERENCES route_import_images(id) ON DELETE SET NULL,
    row_number INTEGER NOT NULL,
    raw_ocr_text TEXT NOT NULL,
    store_name TEXT,
    address TEXT,
    normalized_address TEXT,
    user_corrected_store_name TEXT,
    user_corrected_address TEXT,
    confidence_score NUMERIC(5, 2),
    geocoding_status VARCHAR(30),
    address_id BIGINT REFERENCES addresses(id) ON DELETE SET NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'recognized',
    possible_duplicate_of_id BIGINT REFERENCES route_import_items(id) ON DELETE SET NULL,
    error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CONSTRAINT chk_route_import_items_status
        CHECK (status IN ('recognized', 'needs_review', 'confirmed', 'rejected', 'duplicate'))
);

CREATE INDEX IF NOT EXISTS ix_route_import_items_import_id
    ON route_import_items (import_id);

CREATE INDEX IF NOT EXISTS ix_route_import_items_source_image_id
    ON route_import_items (source_image_id);

CREATE INDEX IF NOT EXISTS ix_route_import_items_status
    ON route_import_items (status);

CREATE INDEX IF NOT EXISTS ix_route_import_items_address_id
    ON route_import_items (address_id);

DROP TRIGGER IF EXISTS trg_route_imports_updated_at ON route_imports;

CREATE TRIGGER trg_route_imports_updated_at
BEFORE UPDATE ON route_imports
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();

DROP TRIGGER IF EXISTS trg_route_import_items_updated_at ON route_import_items;

CREATE TRIGGER trg_route_import_items_updated_at
BEFORE UPDATE ON route_import_items
FOR EACH ROW
EXECUTE FUNCTION set_updated_at();
