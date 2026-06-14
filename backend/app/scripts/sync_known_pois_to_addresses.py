from __future__ import annotations

import argparse
from typing import Any

from app.core.config import settings
from app.utils.address_normalizer import normalize_address


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Materialize usable known_pois rows into the address cache.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print counts without writing to addresses.",
    )
    parser.add_argument(
        "--overwrite-existing",
        action="store_true",
        help="Update existing non-manual address cache rows on normalized_address conflicts.",
    )
    parser.add_argument(
        "--default-city",
        default="санкт-петербург",
        help="Default city used to build the same normalized cache key as route geocoding.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    psycopg2, Json, RealDictCursor = _psycopg()

    with psycopg2.connect(_database_url()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        source_rows = _load_source_rows(cursor)
        unique_rows = _deduplicate_by_normalized_address(source_rows, default_city=args.default_city)
        existing_count = _count_existing(cursor, unique_rows)

        if args.dry_run:
            print("Known POI address sync")
            print(f"Usable known_pois source rows: {len(source_rows)}")
            print(f"Unique route-normalized address keys: {len(unique_rows)}")
            print(f"Already present in addresses by normalized_address: {existing_count}")
            print("Dry run: database was not modified.")
            return 0

        inserted = 0
        updated = 0
        skipped_manual = 0
        for item in unique_rows.values():
            result = _upsert_address(cursor, item, overwrite_existing=args.overwrite_existing)
            if result == "inserted":
                inserted += 1
            elif result == "updated":
                updated += 1
            else:
                skipped_manual += 1

    print("Known POI address sync completed")
    print(f"Usable known_pois source rows: {len(source_rows)}")
    print(f"Unique route-normalized address keys: {len(unique_rows)}")
    print(f"Already present before sync: {existing_count}")
    print(f"Touched addresses: {inserted + updated}")
    print(f"Inserted: {inserted}")
    print(f"Updated/conflicts touched: {updated}")
    print(f"Skipped manual conflicts: {skipped_manual}")
    print(f"Overwrite existing: {args.overwrite_existing}")
    return 0


def _load_source_rows(cursor) -> list[dict[str, Any]]:
    cursor.execute(
        """
        SELECT
            id,
            canonical_brand,
            name,
            original_address,
            latitude,
            longitude,
            confidence_score,
            osm_type,
            osm_id,
            enrichment_source,
            updated_at
        FROM known_pois
        WHERE is_active = true
          AND is_duplicate = false
          AND original_address IS NOT NULL
          AND latitude IS NOT NULL
          AND longitude IS NOT NULL
        ORDER BY
            confidence_score DESC NULLS LAST,
            updated_at DESC,
            id DESC
        """
    )
    return [dict(row) for row in cursor.fetchall()]


def _deduplicate_by_normalized_address(
    rows: list[dict[str, Any]],
    *,
    default_city: str,
) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for row in rows:
        try:
            normalized = normalize_address(row["original_address"], default_city=default_city)
        except ValueError:
            continue

        key = normalized.normalized_address
        if key in result:
            continue

        output = dict(row)
        output["normalized_address"] = key
        output["address_for_geocoding"] = normalized.address_for_geocoding
        result[key] = output
    return result


def _count_existing(cursor, rows: dict[str, dict[str, Any]]) -> int:
    if not rows:
        return 0

    cursor.execute(
        "SELECT COUNT(*) AS existing FROM addresses WHERE normalized_address = ANY(%s)",
        (list(rows),),
    )
    return int(cursor.fetchone()["existing"])


def _upsert_address(cursor, item: dict[str, Any], *, overwrite_existing: bool) -> str:
    from psycopg2.extras import Json

    cursor.execute(
        """
        INSERT INTO addresses (
            original_address,
            normalized_address,
            latitude,
            longitude,
            geom,
            geocoding_status,
            geocoding_provider,
            confidence_score,
            geocoding_query_used,
            geocoding_score,
            display_name,
            osm_type,
            osm_id,
            raw_response,
            source_note,
            last_used_at
        )
        VALUES (
            %(original_address)s,
            %(normalized_address)s,
            %(latitude)s,
            %(longitude)s,
            ST_SetSRID(ST_MakePoint(%(longitude)s, %(latitude)s), 4326),
            'found',
            'known_poi',
            %(confidence_score)s,
            %(normalized_address)s,
            %(geocoding_score)s,
            %(display_name)s,
            %(osm_type)s,
            %(osm_id)s,
            %(raw_response)s,
            'known_pois materialized cache',
            NULL
        )
        ON CONFLICT (normalized_address)
        DO UPDATE SET
            original_address = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.original_address
                ELSE addresses.original_address
            END,
            latitude = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.latitude
                ELSE addresses.latitude
            END,
            longitude = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.longitude
                ELSE addresses.longitude
            END,
            geom = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.geom
                ELSE addresses.geom
            END,
            geocoding_status = CASE
                WHEN %(overwrite_existing)s THEN 'found'
                ELSE addresses.geocoding_status
            END,
            geocoding_provider = CASE
                WHEN %(overwrite_existing)s THEN 'known_poi'
                ELSE addresses.geocoding_provider
            END,
            confidence_score = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.confidence_score
                ELSE addresses.confidence_score
            END,
            geocoding_query_used = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.geocoding_query_used
                ELSE addresses.geocoding_query_used
            END,
            geocoding_score = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.geocoding_score
                ELSE addresses.geocoding_score
            END,
            display_name = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.display_name
                ELSE addresses.display_name
            END,
            osm_type = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.osm_type
                ELSE addresses.osm_type
            END,
            osm_id = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.osm_id
                ELSE addresses.osm_id
            END,
            raw_response = CASE
                WHEN %(overwrite_existing)s THEN EXCLUDED.raw_response
                ELSE COALESCE(addresses.raw_response, EXCLUDED.raw_response)
            END,
            source_note = COALESCE(addresses.source_note, EXCLUDED.source_note),
            updated_at = now()
        WHERE addresses.geocoding_provider IS DISTINCT FROM 'manual'
        RETURNING xmax = 0 AS inserted
        """,
        {
            "original_address": item["original_address"],
            "normalized_address": item["normalized_address"],
            "latitude": item["latitude"],
            "longitude": item["longitude"],
            "confidence_score": round(float(item.get("confidence_score") or 0.0) * 100, 2),
            "geocoding_score": round(float(item.get("confidence_score") or 0.0) * 100, 2),
            "display_name": item["original_address"] or item.get("name") or item["canonical_brand"],
            "osm_type": item.get("osm_type"),
            "osm_id": item.get("osm_id"),
            "raw_response": Json(
                {
                    "source": "known_pois",
                    "known_poi_id": item["id"],
                    "canonical_brand": item["canonical_brand"],
                    "name": item.get("name"),
                    "address": item["original_address"],
                    "enrichment_source": item.get("enrichment_source"),
                }
            ),
            "overwrite_existing": overwrite_existing,
        },
    )
    row = cursor.fetchone()
    if row is None:
        return "skipped"
    return "inserted" if row["inserted"] else "updated"


def _database_url() -> str:
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def _psycopg():
    try:
        import psycopg2
        from psycopg2.extras import Json, RealDictCursor
    except ImportError as exc:
        raise RuntimeError("psycopg2 is required to sync known_pois into addresses.") from exc
    return psycopg2, Json, RealDictCursor


if __name__ == "__main__":
    raise SystemExit(main())
