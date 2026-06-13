from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path
from typing import Any

from app.services.poi_import.models import PoiCandidate


def report_payload(
    *,
    region: str,
    source_file: str,
    stats: dict[str, int],
    candidates: list[PoiCandidate],
) -> dict[str, Any]:
    return {
        "region": region,
        "source_file": source_file,
        "stats": stats,
        "items": [candidate_row(candidate) for candidate in candidates],
    }


def candidate_row(candidate: PoiCandidate) -> dict[str, Any]:
    return {
        "canonical_brand": candidate.canonical_brand,
        "name": candidate.name,
        "address": candidate.original_address,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "confidence_score": candidate.confidence_score,
        "warnings": candidate.warnings,
        "osm_type": candidate.osm_type,
        "osm_id": candidate.osm_id,
        "source": candidate.source,
        "is_duplicate": candidate.is_duplicate,
    }


def write_reports(report: dict[str, Any], output_dir: str | Path) -> dict[str, str]:
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    json_path = output / f"poi_import_{timestamp}.json"
    csv_path = output / f"poi_import_{timestamp}.csv"
    duplicates_path = output / f"poi_duplicates_{timestamp}.csv"
    low_confidence_path = output / f"poi_low_confidence_{timestamp}.csv"

    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(csv_path, report["items"])
    _write_csv(duplicates_path, [item for item in report["items"] if item["is_duplicate"]])
    _write_csv(low_confidence_path, [item for item in report["items"] if item["confidence_score"] < 0.75])
    return {
        "json": str(json_path),
        "csv": str(csv_path),
        "duplicates_csv": str(duplicates_path),
        "low_confidence_csv": str(low_confidence_path),
    }


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "canonical_brand",
        "name",
        "address",
        "latitude",
        "longitude",
        "confidence_score",
        "warnings",
        "osm_type",
        "osm_id",
        "source",
        "is_duplicate",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            output = dict(row)
            output["warnings"] = ";".join(output.get("warnings") or [])
            writer.writerow(output)

