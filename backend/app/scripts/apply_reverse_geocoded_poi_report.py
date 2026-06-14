from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.services.poi_import.address_normalizer import normalized_known_poi_address


DEFAULT_REPORT = Path("/reports/pois/poi_import_20260613_141619_reverse_geocoded_20260614_090544.csv")


@dataclass
class ApplyStats:
    rows: int = 0
    candidates: int = 0
    matched: int = 0
    updated: int = 0
    skipped_existing: int = 0
    skipped_no_address: int = 0
    skipped_not_found: int = 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Apply reverse-geocoded POI report addresses to known_pois.",
    )
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing known_pois original_address values.",
    )
    parser.add_argument(
        "--refresh-confidence",
        action="store_true",
        help="Raise known_pois confidence_score based on reverse address completeness.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Count rows without writing to the database.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.report.exists():
        raise SystemExit(f"Report not found: {args.report}")

    psycopg2, RealDictCursor = _psycopg()
    stats = ApplyStats()
    rows = list(_read_rows(args.report))

    with psycopg2.connect(_database_url()) as conn, conn.cursor(cursor_factory=RealDictCursor) as cursor:
        for row in rows:
            stats.rows += 1
            address = _clean(row.get("address"))
            if not address:
                stats.skipped_no_address += 1
                continue

            osm_type = _clean(row.get("osm_type"))
            osm_id = _as_int(row.get("osm_id"))
            if not osm_type or osm_id is None:
                stats.skipped_no_address += 1
                continue

            stats.candidates += 1
            cursor.execute(
                """
                SELECT id, original_address
                FROM known_pois
                WHERE osm_type = %s AND osm_id = %s
                """,
                (osm_type, osm_id),
            )
            existing = cursor.fetchone()
            if not existing:
                stats.skipped_not_found += 1
                continue

            stats.matched += 1
            update_address = not existing.get("original_address") or args.overwrite
            update_confidence = args.refresh_confidence
            if not update_address and not update_confidence:
                stats.skipped_existing += 1
                continue

            normalized_address = normalized_known_poi_address(
                address,
                default_city=_clean(row.get("reverse_city")),
            )
            reverse_confidence = _reverse_confidence(row)

            if not args.dry_run:
                cursor.execute(
                    """
                    UPDATE known_pois
                    SET
                        original_address = CASE WHEN %s THEN %s ELSE original_address END,
                        normalized_address = CASE WHEN %s THEN %s ELSE normalized_address END,
                        city = CASE WHEN %s THEN COALESCE(NULLIF(%s, ''), city) ELSE city END,
                        district = CASE WHEN %s THEN COALESCE(NULLIF(%s, ''), district) ELSE district END,
                        suburb = CASE WHEN %s THEN COALESCE(NULLIF(%s, ''), suburb) ELSE suburb END,
                        street = CASE WHEN %s THEN COALESCE(NULLIF(%s, ''), street) ELSE street END,
                        house_number = CASE WHEN %s THEN COALESCE(NULLIF(%s, ''), house_number) ELSE house_number END,
                        postcode = CASE WHEN %s THEN COALESCE(NULLIF(%s, ''), postcode) ELSE postcode END,
                        enrichment_source = CASE
                            WHEN %s THEN 'nominatim_reverse_report'
                            ELSE enrichment_source
                        END,
                        confidence_score = CASE
                            WHEN %s THEN GREATEST(COALESCE(confidence_score, 0), %s)
                            ELSE confidence_score
                        END,
                        updated_at = now()
                    WHERE id = %s
                    """,
                    (
                        update_address,
                        address,
                        update_address,
                        normalized_address,
                        update_address,
                        _clean(row.get("reverse_city")),
                        update_address,
                        _clean(row.get("reverse_district")),
                        update_address,
                        _clean(row.get("reverse_suburb")),
                        update_address,
                        _clean(row.get("reverse_street")),
                        update_address,
                        _clean(row.get("reverse_house_number")),
                        update_address,
                        _clean(row.get("reverse_postcode")),
                        update_address,
                        update_confidence,
                        reverse_confidence,
                        existing["id"],
                    ),
                )
            stats.updated += 1

    print("Reverse POI report apply completed")
    print(f"Report: {args.report}")
    print(f"Rows: {stats.rows}")
    print(f"Candidates with address: {stats.candidates}")
    print(f"Matched known_pois: {stats.matched}")
    print(f"Updated: {stats.updated}")
    print(f"Skipped existing address: {stats.skipped_existing}")
    print(f"Skipped no address: {stats.skipped_no_address}")
    print(f"Skipped not found in DB: {stats.skipped_not_found}")
    if args.dry_run:
        print("Dry run: database was not modified.")

    return 0


def _read_rows(path: Path):
    with path.open("r", newline="", encoding="utf-8-sig") as handle:
        yield from csv.DictReader(handle)


def _database_url() -> str:
    return (
        f"postgresql://{settings.POSTGRES_USER}:{settings.POSTGRES_PASSWORD}"
        f"@{settings.POSTGRES_HOST}:{settings.POSTGRES_PORT}/{settings.POSTGRES_DB}"
    )


def _psycopg():
    try:
        import psycopg2
        from psycopg2.extras import RealDictCursor
    except ImportError as exc:
        raise RuntimeError("psycopg2 is required to update known_pois.") from exc
    return psycopg2, RealDictCursor


def _clean(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


def _as_int(value: Any) -> int | None:
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return None


def _reverse_confidence(row: dict[str, Any]) -> float:
    if _clean(row.get("reverse_house_number")):
        return 0.95
    if _clean(row.get("reverse_street")):
        return 0.75
    if _clean(row.get("address")):
        return 0.65
    return 0.0


if __name__ == "__main__":
    raise SystemExit(main())
