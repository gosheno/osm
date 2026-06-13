from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.services.poi_import.brand_normalizer import normalize_brand_text
from app.services.poi_import.models import ChainConfig, PoiCandidate


@dataclass(frozen=True)
class ImportWriteResult:
    imported: int = 0
    updated: int = 0


class PoiRepository:
    def __init__(self, db_url: str) -> None:
        self.db_url = db_url

    def ensure_aliases(self, chains: list[ChainConfig]) -> None:
        psycopg2, Json, _RealDictCursor = _psycopg()
        with psycopg2.connect(self.db_url) as conn, conn.cursor() as cursor:
            for chain in chains:
                for alias in [chain.canonical_brand, *chain.aliases]:
                    cursor.execute(
                        """
                        INSERT INTO poi_brand_aliases (
                            canonical_brand, alias, normalized_alias, priority, is_active
                        )
                        VALUES (%s, %s, %s, %s, true)
                        ON CONFLICT (canonical_brand, normalized_alias)
                        DO UPDATE SET alias = EXCLUDED.alias, priority = EXCLUDED.priority, is_active = true
                        """,
                        (
                            chain.canonical_brand,
                            alias,
                            normalize_brand_text(alias),
                            chain.priority,
                        ),
                    )

    def create_run(self, *, source_file: str, region: str, status: str = "running") -> int:
        psycopg2, _Json, _RealDictCursor = _psycopg()
        with psycopg2.connect(self.db_url) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO poi_import_runs (status, source_file, region)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (status, source_file, region),
            )
            return int(cursor.fetchone()[0])

    def finish_run(
        self,
        run_id: int,
        *,
        status: str,
        counters: dict[str, int],
        report: dict[str, Any],
        error_message: str | None = None,
    ) -> None:
        psycopg2, Json, _RealDictCursor = _psycopg()
        with psycopg2.connect(self.db_url) as conn, conn.cursor() as cursor:
            cursor.execute(
                """
                UPDATE poi_import_runs
                SET
                    finished_at = now(),
                    status = %s,
                    total_objects_scanned = %s,
                    total_candidates = %s,
                    total_imported = %s,
                    total_updated = %s,
                    total_skipped = %s,
                    total_duplicates = %s,
                    total_errors = %s,
                    error_message = %s,
                    report = %s
                WHERE id = %s
                """,
                (
                    status,
                    counters.get("objects_scanned", 0),
                    counters.get("candidates", 0),
                    counters.get("imported", 0),
                    counters.get("updated", 0),
                    counters.get("skipped", 0),
                    counters.get("duplicates", 0),
                    counters.get("errors", 0),
                    error_message,
                    Json(report),
                    run_id,
                ),
            )

    def upsert_candidates(self, candidates: Iterable[PoiCandidate], *, update_existing: bool) -> ImportWriteResult:
        psycopg2, _Json, RealDictCursor = _psycopg()
        imported = 0
        updated = 0
        candidates = list(candidates)
        existing_ids = self._existing_ids((candidate.osm_key for candidate in candidates))
        with psycopg2.connect(self.db_url) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
            key_to_id: dict[tuple[str, int], int] = {}
            for candidate in candidates:
                existed = candidate.osm_key in existing_ids
                if existed and not update_existing:
                    continue
                cursor.execute(_UPSERT_SQL, _candidate_params(candidate))
                row = cursor.fetchone()
                key_to_id[candidate.osm_key] = int(row["id"])
                if existed:
                    updated += 1
                else:
                    imported += 1

            for candidate in candidates:
                if not candidate.is_duplicate or not candidate.duplicate_of_key:
                    continue
                duplicate_id = key_to_id.get(candidate.osm_key) or existing_ids.get(candidate.osm_key)
                keeper_id = key_to_id.get(candidate.duplicate_of_key) or existing_ids.get(candidate.duplicate_of_key)
                if duplicate_id and keeper_id:
                    cursor.execute(
                        """
                        UPDATE known_pois
                        SET is_duplicate = true, duplicate_of_id = %s
                        WHERE id = %s
                        """,
                        (keeper_id, duplicate_id),
                    )
        return ImportWriteResult(imported=imported, updated=updated)

    def deactivate_missing(self, source_keys: set[tuple[str, int]], *, source: str = "osm_pbf") -> int:
        psycopg2, _Json, _RealDictCursor = _psycopg()
        if not source_keys:
            return 0
        with psycopg2.connect(self.db_url) as conn, conn.cursor() as cursor:
            cursor.execute(
                "SELECT osm_type, osm_id FROM known_pois WHERE source = %s AND is_active = true",
                (source,),
            )
            existing = {(row[0], int(row[1])) for row in cursor.fetchall()}
            missing = existing - source_keys
            for osm_type, osm_id in missing:
                cursor.execute(
                    """
                    UPDATE known_pois
                    SET is_active = false
                    WHERE osm_type = %s AND osm_id = %s
                    """,
                    (osm_type, osm_id),
                )
            return len(missing)

    def _existing_ids(self, keys: Iterable[tuple[str, int]]) -> dict[tuple[str, int], int]:
        psycopg2, _Json, _RealDictCursor = _psycopg()
        keys = list(keys)
        if not keys:
            return {}
        result: dict[tuple[str, int], int] = {}
        with psycopg2.connect(self.db_url) as conn, conn.cursor() as cursor:
            for osm_type, osm_id in keys:
                cursor.execute(
                    "SELECT id FROM known_pois WHERE osm_type = %s AND osm_id = %s",
                    (osm_type, osm_id),
                )
                row = cursor.fetchone()
                if row:
                    result[(osm_type, osm_id)] = int(row[0])
        return result


def _candidate_params(candidate: PoiCandidate) -> dict[str, Any]:
    _psycopg2, Json, _RealDictCursor = _psycopg()
    return {
        "osm_type": candidate.osm_type,
        "osm_id": candidate.osm_id,
        "canonical_brand": candidate.canonical_brand,
        "detected_brand": candidate.detected_brand,
        "name": candidate.name,
        "operator": candidate.operator,
        "shop_type": candidate.shop_type,
        "amenity_type": candidate.amenity_type,
        "original_address": candidate.original_address,
        "normalized_address": candidate.normalized_address,
        "country": candidate.country,
        "region": candidate.region,
        "city": candidate.city,
        "district": candidate.district,
        "suburb": candidate.suburb,
        "street": candidate.street,
        "house_number": candidate.house_number,
        "postcode": candidate.postcode,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "phone": candidate.phone,
        "website": candidate.website,
        "opening_hours": candidate.opening_hours,
        "source": candidate.source,
        "enrichment_source": candidate.enrichment_source,
        "raw_tags": Json(candidate.raw_tags),
        "confidence_score": candidate.confidence_score,
        "is_duplicate": candidate.is_duplicate,
    }


_UPSERT_SQL = """
INSERT INTO known_pois (
    osm_type, osm_id, canonical_brand, detected_brand, name, operator,
    shop_type, amenity_type, original_address, normalized_address,
    country, region, city, district, suburb, street, house_number, postcode,
    latitude, longitude, geom, phone, website, opening_hours,
    source, enrichment_source, raw_tags, confidence_score, is_active, is_duplicate
)
VALUES (
    %(osm_type)s, %(osm_id)s, %(canonical_brand)s, %(detected_brand)s, %(name)s, %(operator)s,
    %(shop_type)s, %(amenity_type)s, %(original_address)s, %(normalized_address)s,
    %(country)s, %(region)s, %(city)s, %(district)s, %(suburb)s, %(street)s, %(house_number)s, %(postcode)s,
    %(latitude)s, %(longitude)s, ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326),
    %(phone)s, %(website)s, %(opening_hours)s, %(source)s, %(enrichment_source)s,
    %(raw_tags)s, %(confidence_score)s, true, %(is_duplicate)s
)
ON CONFLICT (osm_type, osm_id)
DO UPDATE SET
    canonical_brand = EXCLUDED.canonical_brand,
    detected_brand = EXCLUDED.detected_brand,
    name = EXCLUDED.name,
    operator = EXCLUDED.operator,
    shop_type = EXCLUDED.shop_type,
    amenity_type = EXCLUDED.amenity_type,
    original_address = EXCLUDED.original_address,
    normalized_address = EXCLUDED.normalized_address,
    country = EXCLUDED.country,
    region = EXCLUDED.region,
    city = EXCLUDED.city,
    district = EXCLUDED.district,
    suburb = EXCLUDED.suburb,
    street = EXCLUDED.street,
    house_number = EXCLUDED.house_number,
    postcode = EXCLUDED.postcode,
    latitude = EXCLUDED.latitude,
    longitude = EXCLUDED.longitude,
    geom = EXCLUDED.geom,
    phone = EXCLUDED.phone,
    website = EXCLUDED.website,
    opening_hours = EXCLUDED.opening_hours,
    source = EXCLUDED.source,
    enrichment_source = EXCLUDED.enrichment_source,
    raw_tags = EXCLUDED.raw_tags,
    confidence_score = EXCLUDED.confidence_score,
    is_active = true,
    is_duplicate = EXCLUDED.is_duplicate,
    updated_at = now()
RETURNING id
"""


def _psycopg():
    try:
        import psycopg2
        from psycopg2.extras import Json, RealDictCursor
    except ImportError as exc:
        raise RuntimeError(
            "psycopg2 is required for database writes. Install backend requirements "
            "or use --dry-run without DB writes."
        ) from exc
    return psycopg2, Json, RealDictCursor
