from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.services.poi_import.brand_normalizer import BrandAliasMatcher
from app.services.poi_import.config import DEFAULT_CONFIG_PATH, load_poi_config
from app.services.poi_import.duplicate_detector import mark_duplicates
from app.services.poi_import.nominatim_enricher import NominatimEnricher
from app.services.poi_import.osm_pbf_reader import read_pbf_candidates
from app.services.poi_import.poi_repository import PoiRepository
from app.services.poi_import.report_writer import report_payload, write_reports


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import known chain store POIs from a local .osm.pbf file.",
    )
    parser.add_argument("--pbf", required=True, help="Local .osm.pbf file.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="POI chain YAML config.")
    parser.add_argument("--db-url", required=True, help="PostgreSQL URL.")
    parser.add_argument("--region", default="spb_lenobl", help="Region config name.")
    parser.add_argument("--dry-run", action="store_true", help="Extract and report without writing to DB.")
    parser.add_argument("--limit", type=int, default=None, help="Process only N matching POIs.")
    parser.add_argument("--brand", default=None, help="Import only one canonical brand.")
    parser.add_argument("--enrich-with-nominatim", action="store_true", help="Use local Nominatim reverse enrichment.")
    parser.add_argument("--nominatim-url", default=None, help="Local Nominatim base URL.")
    parser.add_argument("--update-existing", action="store_true", help="Update existing known_pois rows.")
    parser.add_argument("--deactivate-missing", action="store_true", help="Deactivate known POIs missing from this import.")
    parser.add_argument("--export-report", default=None, help="Directory for JSON/CSV reports.")
    parser.add_argument("--verbose", action="store_true", help="Print more progress details.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_poi_config(args.config)
    if args.region != config.region.name:
        raise SystemExit(f"Region {args.region!r} is not defined by {args.config}")

    matcher = BrandAliasMatcher(config.chains)
    if args.brand and args.brand not in {chain.canonical_brand for chain in config.chains}:
        raise SystemExit(f"Unknown brand {args.brand!r}. Check {args.config}")

    pbf_path = Path(args.pbf)
    if not pbf_path.exists():
        raise SystemExit(f"PBF file not found: {pbf_path}")

    candidates, stats = read_pbf_candidates(
        pbf_path=pbf_path,
        config=config,
        matcher=matcher,
        brand=args.brand,
        limit=args.limit,
    )

    if args.enrich_with_nominatim:
        if not args.nominatim_url:
            raise SystemExit("--nominatim-url is required with --enrich-with-nominatim")
        enricher = NominatimEnricher(args.nominatim_url)
        enriched = []
        for candidate in candidates:
            try:
                enriched.append(enricher.enrich_if_needed(candidate))
            except Exception as exc:
                candidate.warnings.append("NOMINATIM_ENRICHMENT_FAILED")
                stats["errors"] = stats.get("errors", 0) + 1
                if args.verbose:
                    print(f"Enrichment failed for {candidate.osm_type}/{candidate.osm_id}: {exc}", file=sys.stderr)
                enriched.append(candidate)
        candidates = enriched

    candidates = mark_duplicates(candidates)
    stats["duplicates"] = sum(1 for candidate in candidates if candidate.is_duplicate)

    write_stats = {"imported": 0, "updated": 0, "deactivated": 0}
    run_id: int | None = None
    repository: PoiRepository | None = None
    if not args.dry_run:
        repository = PoiRepository(args.db_url)
        run_id = repository.create_run(source_file=str(pbf_path), region=args.region)
        try:
            repository.ensure_aliases(config.chains)
            result = repository.upsert_candidates(candidates, update_existing=args.update_existing)
            write_stats["imported"] = result.imported
            write_stats["updated"] = result.updated
            if args.deactivate_missing:
                write_stats["deactivated"] = repository.deactivate_missing(
                    {candidate.osm_key for candidate in candidates}
                )
        except Exception as exc:
            if run_id is not None:
                repository.finish_run(
                    run_id,
                    status="failed",
                    counters={**stats, **write_stats},
                    report={},
                    error_message=str(exc),
                )
            raise

    report_stats = {**stats, **write_stats}
    report = report_payload(
        region=args.region,
        source_file=str(pbf_path),
        stats=report_stats,
        candidates=candidates,
    )
    report_paths = {}
    if args.export_report:
        report_paths = write_reports(report, args.export_report)

    if repository is not None and run_id is not None:
        repository.finish_run(
            run_id,
            status="completed",
            counters=report_stats,
            report=report,
        )

    print()
    print("POI import completed")
    print()
    print(f"Region: {args.region}")
    print(f"Source: {pbf_path}")
    print()
    print(f"Scanned objects: {stats.get('objects_scanned', 0):,}")
    print(f"Candidates found: {stats.get('candidates', 0):,}")
    print(f"Imported: {write_stats['imported']:,}")
    print(f"Updated: {write_stats['updated']:,}")
    print(f"Skipped: {stats.get('skipped', 0):,}")
    print(f"Duplicates: {stats.get('duplicates', 0):,}")
    print(f"Errors: {stats.get('errors', 0):,}")
    if report_paths:
        print()
        print("Reports:")
        for name, path in report_paths.items():
            print(f"  {name}: {path}")
    if args.dry_run:
        print()
        print("Dry run: database was not modified.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

