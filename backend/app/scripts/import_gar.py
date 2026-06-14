from __future__ import annotations

import argparse
import asyncio
import json

from app.db.session import AsyncSessionLocal
from app.services.gar_importer import GarImportService


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Import GAR/FIAS XML data.")
    parser.add_argument("--region", default="spb_lenobl", help="Region preset or comma-separated region codes.")
    parser.add_argument("--path", required=True, help="Path to GAR/FIAS XML folder, XML file, or ZIP archive.")
    return parser.parse_args()


async def main() -> None:
    args = parse_args()
    async with AsyncSessionLocal() as session:
        service = GarImportService(session)
        import_id = await service.create_import_run(region=args.region, source_path=args.path)
        stats = await service.import_path(
            import_id=import_id,
            region=args.region,
            source_path=args.path,
        )
        report = stats.to_report()
        report["import_id"] = import_id
        print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
