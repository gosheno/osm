from __future__ import annotations

import argparse
import asyncio
import csv
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from app.clients.nominatim_client import NominatimClient, ReverseGeocodingCandidate
from app.core.config import settings


PUBLIC_NOMINATIM_HOST = "nominatim.openstreetmap.org"
DEFAULT_REPORTS_DIR = Path("/reports/pois") if Path("/reports").exists() else Path("reports/pois")
OUTPUT_COLUMNS = [
    "reverse_status",
    "reverse_address",
    "reverse_display_name",
    "reverse_city",
    "reverse_district",
    "reverse_suburb",
    "reverse_street",
    "reverse_house_number",
    "reverse_postcode",
    "reverse_osm_type",
    "reverse_osm_id",
    "reverse_error",
]


@dataclass(frozen=True)
class ReverseResult:
    status: str
    address: str | None = None
    display_name: str | None = None
    address_details: dict[str, Any] | None = None
    osm_type: str | None = None
    osm_id: int | None = None
    error: str | None = None


@dataclass
class RunStats:
    files: int = 0
    rows: int = 0
    requested: int = 0
    skipped: int = 0
    found: int = 0
    not_found: int = 0
    errors: int = 0
    filled: int = 0

    def add(self, other: "RunStats") -> None:
        self.files += other.files
        self.rows += other.rows
        self.requested += other.requested
        self.skipped += other.skipped
        self.found += other.found
        self.not_found += other.not_found
        self.errors += other.errors
        self.filled += other.filled


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Reverse-geocode POI CSV/JSON reports using the backend NominatimClient settings.",
    )
    parser.add_argument(
        "--reports-dir",
        type=Path,
        default=DEFAULT_REPORTS_DIR,
        help="Directory with POI reports. Used when --input is not passed.",
    )
    parser.add_argument(
        "--input",
        type=Path,
        action="append",
        default=[],
        help="Input report file. Can be passed multiple times. Supports .csv and .json.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Directory for enriched reports. Defaults to each input file directory.",
    )
    parser.add_argument(
        "--nominatim-url",
        default=None,
        help="Override settings.NOMINATIM_BASE_URL for this run.",
    )
    parser.add_argument(
        "--allow-public-nominatim",
        action="store_true",
        help="Allow using nominatim.openstreetmap.org. Use only for tiny manual checks.",
    )
    parser.add_argument("--language", default=None, help="Override NOMINATIM_ACCEPT_LANGUAGE.")
    parser.add_argument("--all", action="store_true", help="Reverse-geocode every row.")
    parser.add_argument(
        "--overwrite-address",
        action="store_true",
        help="Replace existing address values with reverse-geocoded addresses.",
    )
    parser.add_argument(
        "--no-fill-address",
        action="store_true",
        help="Keep the original address column and write only reverse_* columns.",
    )
    parser.add_argument("--limit", type=int, default=None, help="Maximum reverse requests.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Read reports and print what would be requested without calling Nominatim.",
    )
    parser.add_argument(
        "--skip-health-check",
        action="store_true",
        help="Do not check Nominatim /status before processing reports.",
    )
    parser.add_argument("--fail-fast", action="store_true", help="Stop on the first error.")
    return parser.parse_args(argv)


async def async_main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.nominatim_url:
        settings.NOMINATIM_BASE_URL = args.nominatim_url

    inputs = resolve_inputs(args.input, args.reports_dir)
    if not inputs:
        raise SystemExit(f"No POI report files found in {args.reports_dir}")

    client = NominatimClient()
    if not args.dry_run:
        ensure_allowed_nominatim_url(client.base_url, args.allow_public_nominatim)
        if not args.skip_health_check:
            await ensure_nominatim_available(client)

    print(f"Nominatim URL: {client.base_url}")
    print(f"Reports: {args.reports_dir}")

    cache: dict[str, ReverseResult] = {}
    total = RunStats()
    requested_count = 0
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    for input_path in inputs:
        if input_path.suffix.lower() == ".csv":
            stats, requested_count = await process_csv(
                input_path=input_path,
                output_dir=args.output_dir,
                timestamp=timestamp,
                args=args,
                client=client,
                cache=cache,
                requested_count=requested_count,
            )
        elif input_path.suffix.lower() == ".json":
            stats, requested_count = await process_json(
                input_path=input_path,
                output_dir=args.output_dir,
                timestamp=timestamp,
                args=args,
                client=client,
                cache=cache,
                requested_count=requested_count,
            )
        else:
            print(f"Skipping unsupported report type: {input_path}", file=sys.stderr)
            continue

        total.add(stats)

    print()
    print("Reverse geocoding completed")
    print(f"Files: {total.files}")
    print(f"Rows: {total.rows}")
    print(f"Requested: {total.requested}")
    print(f"Skipped: {total.skipped}")
    print(f"Found: {total.found}")
    print(f"Not found: {total.not_found}")
    print(f"Errors: {total.errors}")
    print(f"Address filled: {total.filled}")
    if args.dry_run:
        print("Dry run: Nominatim was not called and no files were written.")

    return 1 if total.errors else 0


async def process_csv(
    *,
    input_path: Path,
    output_dir: Path | None,
    timestamp: str,
    args: argparse.Namespace,
    client: NominatimClient,
    cache: dict[str, ReverseResult],
    requested_count: int,
) -> tuple[RunStats, int]:
    stats = RunStats(files=1)
    with input_path.open("r", newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        rows = [dict(row) for row in reader]
        fieldnames = list(reader.fieldnames or [])

    stats.rows = len(rows)
    enriched_rows: list[dict[str, Any]] = []
    for row in rows:
        result, requested_count, requested = await resolve_row(
            row,
            args=args,
            client=client,
            cache=cache,
            requested_count=requested_count,
        )
        update_stats(stats, result, requested)
        enriched_rows.append(apply_result(row, result=result, args=args, stats=stats))

    if not args.dry_run:
        output_path = output_path_for(input_path, output_dir, timestamp)
        write_csv(output_path, enriched_rows, fieldnames)
        print(f"Wrote {output_path}")
    else:
        print(f"Would process {input_path}: rows={stats.rows}, requested={stats.requested}")

    return stats, requested_count


async def process_json(
    *,
    input_path: Path,
    output_dir: Path | None,
    timestamp: str,
    args: argparse.Namespace,
    client: NominatimClient,
    cache: dict[str, ReverseResult],
    requested_count: int,
) -> tuple[RunStats, int]:
    stats = RunStats(files=1)
    payload = json.loads(input_path.read_text(encoding="utf-8-sig"))
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise ValueError(f"JSON report has no items list: {input_path}")

    stats.rows = len(items)
    enriched_items: list[dict[str, Any]] = []
    for item in items:
        row = dict(item) if isinstance(item, dict) else {}
        result, requested_count, requested = await resolve_row(
            row,
            args=args,
            client=client,
            cache=cache,
            requested_count=requested_count,
        )
        update_stats(stats, result, requested)
        enriched_items.append(apply_result(row, result=result, args=args, stats=stats))

    if not args.dry_run:
        payload["items"] = enriched_items
        payload["reverse_geocoding"] = {
            "generated_at": datetime.now().isoformat(timespec="seconds"),
            "nominatim_url": client.base_url,
            "stats": stats.__dict__,
        }
        output_path = output_path_for(input_path, output_dir, timestamp)
        output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"Wrote {output_path}")
    else:
        print(f"Would process {input_path}: rows={stats.rows}, requested={stats.requested}")

    return stats, requested_count


async def resolve_row(
    row: dict[str, Any],
    *,
    args: argparse.Namespace,
    client: NominatimClient,
    cache: dict[str, ReverseResult],
    requested_count: int,
) -> tuple[ReverseResult, int, bool]:
    if should_skip_row(row, args):
        return ReverseResult(status="skipped_existing_address"), requested_count, False

    if args.limit is not None and requested_count >= args.limit:
        return ReverseResult(status="skipped_limit"), requested_count, False

    latitude = as_float(row.get("latitude"))
    longitude = as_float(row.get("longitude"))
    if latitude is None or longitude is None:
        return ReverseResult(status="error", error="Missing or invalid latitude/longitude"), requested_count, False

    key = f"{latitude:.7f},{longitude:.7f}"
    if key in cache:
        return cache[key], requested_count, False

    if args.dry_run:
        result = ReverseResult(status="dry_run")
    else:
        try:
            candidate = await client.reverse(
                latitude,
                longitude,
                language=args.language,
            )
            result = result_from_candidate(candidate)
        except Exception as exc:
            result = ReverseResult(status="error", error=str(exc))
            if args.fail_fast:
                raise

    cache[key] = result
    return result, requested_count + 1, True


def result_from_candidate(candidate: ReverseGeocodingCandidate | None) -> ReverseResult:
    if candidate is None:
        return ReverseResult(status="not_found", error="Nominatim returned no address")

    address = build_compact_address(candidate.address, candidate.display_name)
    return ReverseResult(
        status="found",
        address=address or candidate.display_name,
        display_name=candidate.display_name,
        address_details=candidate.address,
        osm_type=candidate.osm_type,
        osm_id=candidate.osm_id,
    )


def apply_result(
    row: dict[str, Any],
    *,
    result: ReverseResult,
    args: argparse.Namespace,
    stats: RunStats,
) -> dict[str, Any]:
    output = dict(row)
    details = result.address_details or {}
    output.update(result_to_columns(result, details))

    existing_address = as_text(output.get("address"))
    should_fill = (
        not args.no_fill_address
        and result.status == "found"
        and bool(result.address)
        and (args.overwrite_address or not existing_address)
    )
    if should_fill:
        output["address"] = result.address
        output["warnings"] = update_warnings(output.get("warnings"))
        stats.filled += 1

    return output


def result_to_columns(result: ReverseResult, details: dict[str, Any]) -> dict[str, Any]:
    return {
        "reverse_status": result.status,
        "reverse_address": result.address or "",
        "reverse_display_name": result.display_name or "",
        "reverse_city": first_text(details, "city", "town", "village", "hamlet", "municipality"),
        "reverse_district": first_text(details, "city_district", "district", "county"),
        "reverse_suburb": first_text(details, "suburb", "neighbourhood", "quarter"),
        "reverse_street": first_text(details, "road", "pedestrian", "footway", "path"),
        "reverse_house_number": first_text(details, "house_number"),
        "reverse_postcode": first_text(details, "postcode"),
        "reverse_osm_type": result.osm_type or "",
        "reverse_osm_id": result.osm_id or "",
        "reverse_error": result.error or "",
    }


def update_stats(stats: RunStats, result: ReverseResult, requested: bool) -> None:
    if requested:
        stats.requested += 1

    if result.status == "found":
        stats.found += 1
    elif result.status == "not_found":
        stats.not_found += 1
    elif result.status == "error":
        stats.errors += 1
    elif result.status.startswith("skipped"):
        stats.skipped += 1


def should_skip_row(row: dict[str, Any], args: argparse.Namespace) -> bool:
    if args.all:
        return False
    return bool(as_text(row.get("address")))


def resolve_inputs(explicit_inputs: list[Path], reports_dir: Path) -> list[Path]:
    if explicit_inputs:
        return [path for path in explicit_inputs if path.exists()]

    if not reports_dir.exists():
        return []

    inputs: list[Path] = []
    for pattern in ("poi_import_*.csv", "poi_low_confidence_*.csv", "poi_duplicates_*.csv"):
        inputs.extend(reports_dir.glob(pattern))

    return sorted(path for path in inputs if "_reverse_geocoded_" not in path.stem)


def output_path_for(input_path: Path, output_dir: Path | None, timestamp: str) -> Path:
    directory = output_dir or input_path.parent
    directory.mkdir(parents=True, exist_ok=True)
    return directory / f"{input_path.stem}_reverse_geocoded_{timestamp}{input_path.suffix}"


def write_csv(path: Path, rows: list[dict[str, Any]], input_fieldnames: list[str]) -> None:
    fieldnames = list(input_fieldnames)
    for column in OUTPUT_COLUMNS:
        if column not in fieldnames:
            fieldnames.append(column)

    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def build_compact_address(address: dict[str, Any], display_name: str | None) -> str | None:
    if not address:
        return display_name

    city = first_text(address, "city", "town", "village", "hamlet", "municipality")
    street = first_text(address, "road", "pedestrian", "footway", "path")
    house_number = first_text(address, "house_number")
    suburb = first_text(address, "suburb", "neighbourhood", "quarter")

    parts: list[str] = []
    if city:
        parts.append(city)
    elif suburb:
        parts.append(suburb)

    if street and house_number:
        parts.append(f"{street}, {house_number}")
    elif street:
        parts.append(street)
    elif house_number:
        parts.append(house_number)

    compact = ", ".join(part for part in parts if part)
    return compact or display_name


def update_warnings(value: Any) -> list[str] | str:
    if isinstance(value, list):
        warnings = [str(item).strip() for item in value if str(item).strip()]
    else:
        warnings = [item.strip() for item in str(value or "").split(";") if item.strip()]

    warnings = [warning for warning in warnings if warning != "ADDRESS_MISSING"]
    if "REVERSE_GEOCODED" not in warnings:
        warnings.append("REVERSE_GEOCODED")
    if isinstance(value, list):
        return warnings
    return ";".join(warnings)


def ensure_allowed_nominatim_url(base_url: str, allow_public: bool) -> None:
    parsed = urlparse(base_url)
    if parsed.hostname == PUBLIC_NOMINATIM_HOST and not allow_public:
        raise SystemExit(
            "Configured NOMINATIM_BASE_URL points to public Nominatim. "
            "For report enrichment set NOMINATIM_BASE_URL to a local instance, "
            "or pass --allow-public-nominatim only for a tiny --limit check."
        )


async def ensure_nominatim_available(client: NominatimClient) -> None:
    health = await client.health_check()
    if health.available:
        return

    detail = health.error or health.body or "no response"
    status = health.status_code if health.status_code is not None else "no status"
    raise SystemExit(
        "Nominatim is not available before report processing. "
        f"url={client.base_url}, status={status}, error={detail}"
    )


def first_text(source: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = as_text(source.get(key))
        if value:
            return value
    return ""


def as_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def as_float(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return None


def main(argv: list[str] | None = None) -> int:
    return asyncio.run(async_main(argv))


if __name__ == "__main__":
    raise SystemExit(main())
