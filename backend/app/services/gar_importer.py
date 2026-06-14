from __future__ import annotations

import json
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from xml.etree.ElementTree import iterparse

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


REGION_PRESETS = {
    "spb": ["78"],
    "saint_petersburg": ["78"],
    "sankt_peterburg": ["78"],
    "lenobl": ["47"],
    "lenoblast": ["47"],
    "spb_lenobl": ["78", "47"],
}

REGION_LABELS = {
    "78": ("Санкт-Петербург", "г"),
    "47": ("Ленинградская область", "обл"),
}

ADDRESS_OBJECT_TAGS = {"OBJECT"}
HOUSE_TAGS = {"HOUSE"}
HIERARCHY_TAGS = {"ITEM"}
BATCH_SIZE = 1000


class GarImportError(Exception):
    pass


@dataclass(frozen=True)
class HierarchyItem:
    object_id: int
    parent_object_id: int | None
    region_code: str | None
    path: str | None
    is_active: bool


@dataclass
class GarImportStats:
    region: str
    address_objects_imported: int = 0
    houses_imported: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    started_at: str | None = None
    finished_at: str | None = None

    def to_report(self) -> dict[str, Any]:
        return {
            "region": self.region,
            "address_objects_imported": self.address_objects_imported,
            "houses_imported": self.houses_imported,
            "updated": self.updated,
            "skipped": self.skipped,
            "errors": self.errors,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_region_codes(region: str | None) -> list[str]:
    if not region:
        return []

    value = region.strip().lower().replace("-", "_")
    if value in REGION_PRESETS:
        return REGION_PRESETS[value]

    codes = [
        item.strip()
        for item in value.replace(";", ",").split(",")
        if item.strip()
    ]
    return [code.zfill(2) if code.isdigit() else code for code in codes]


def local_tag(tag: str) -> str:
    return tag.rsplit("}", 1)[-1].upper()


def elem_attrs(elem) -> dict[str, str]:
    return {key.upper(): value for key, value in elem.attrib.items()}


def first_attr(attrs: dict[str, str], *names: str) -> str | None:
    for name in names:
        value = attrs.get(name.upper())
        if value not in (None, ""):
            return value
    return None


def safe_int(value: Any) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def safe_bool(value: Any, *, default: bool = True) -> bool:
    if value in (None, ""):
        return default
    return str(value).strip().lower() in {"1", "true", "t", "yes", "y"}


def normalize_type_name(value: str | None) -> str | None:
    if not value:
        return None
    normalized = value.strip().replace(".", "").lower()
    replacements = {
        "ул": "улица",
        "пр-кт": "проспект",
        "просп": "проспект",
        "пер": "переулок",
        "наб": "набережная",
        "пл": "площадь",
        "ш": "шоссе",
        "б-р": "бульвар",
        "бул": "бульвар",
    }
    return replacements.get(normalized, value.strip())


def full_object_name(name: str, type_name: str | None) -> str:
    name = name.strip()
    type_name = normalize_type_name(type_name)
    if not type_name:
        return name
    if name.lower().startswith(f"{type_name.lower()} "):
        return name
    return f"{type_name} {name}"


def is_xml_file(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".xml"


def classify_xml_file(path: Path) -> str | None:
    name = path.name.upper()
    if "HIERARCHY" in name:
        return "hierarchy"
    if "HOUSE" in name or "HOUSES" in name:
        return "houses"
    if "ADDR_OBJ" in name or "ADDRESS_OBJECT" in name or "OBJECTS" in name:
        return "objects"
    return None


class GarImportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_import_run(self, *, region: str, source_path: str) -> int:
        result = await self.db.execute(
            text(
                """
                INSERT INTO gar_import_runs (region, source_path, status)
                VALUES (:region, :source_path, 'pending')
                RETURNING id
                """
            ),
            {"region": region, "source_path": source_path},
        )
        await self.db.commit()
        return int(result.scalar_one())

    async def get_import_run(self, import_id: int) -> dict[str, Any] | None:
        result = await self.db.execute(
            text(
                """
                SELECT
                    id AS import_id,
                    region,
                    source_path,
                    status,
                    address_objects_imported,
                    houses_imported,
                    updated,
                    skipped,
                    errors,
                    error_message,
                    report,
                    started_at,
                    finished_at
                FROM gar_import_runs
                WHERE id = :import_id
                """
            ),
            {"import_id": import_id},
        )
        row = result.mappings().first()
        if row is None:
            return None

        data = dict(row)
        for key in ("started_at", "finished_at"):
            if data.get(key) is not None:
                data[key] = data[key].isoformat()
        return data

    async def import_path(
        self,
        *,
        import_id: int,
        region: str,
        source_path: str,
    ) -> GarImportStats:
        stats = GarImportStats(region=region, started_at=utc_now_iso())
        await self._mark_run(import_id, status="running")

        try:
            source = Path(source_path)
            if not source.exists():
                raise GarImportError(f"GAR source path not found: {source}")

            with tempfile.TemporaryDirectory(prefix="gar-import-") as temp_dir:
                work_path = self._prepare_source(source, Path(temp_dir))
                xml_files = self._collect_xml_files(work_path)
                if not xml_files:
                    raise GarImportError(f"No XML files found in GAR source: {source}")

                region_codes = normalize_region_codes(region)
                await self._upsert_regions(region_codes)

                hierarchy = self._read_hierarchy(xml_files, region_codes)

                for path in xml_files:
                    kind = classify_xml_file(path)
                    if kind == "objects":
                        stats.address_objects_imported += await self._import_objects_file(
                            path,
                            hierarchy=hierarchy,
                            region_codes=region_codes,
                        )
                    elif kind == "houses":
                        stats.houses_imported += await self._import_houses_file(
                            path,
                            hierarchy=hierarchy,
                            region_codes=region_codes,
                        )
                    elif kind is None:
                        stats.skipped += 1

            stats.finished_at = utc_now_iso()
            await self._finish_run(import_id, status="completed", stats=stats)
            return stats
        except Exception as exc:
            stats.errors += 1
            stats.finished_at = utc_now_iso()
            await self._finish_run(
                import_id,
                status="failed",
                stats=stats,
                error_message=str(exc),
            )
            raise

    def _prepare_source(self, source: Path, temp_dir: Path) -> Path:
        if source.is_file() and source.suffix.lower() == ".zip":
            with zipfile.ZipFile(source) as archive:
                archive.extractall(temp_dir)
            return temp_dir
        return source

    def _collect_xml_files(self, source: Path) -> list[Path]:
        if is_xml_file(source):
            return [source]
        if source.is_dir():
            return sorted(
                path
                for path in source.rglob("*")
                if path.is_file() and path.suffix.lower() == ".xml"
            )
        return []

    def _read_hierarchy(
        self,
        xml_files: list[Path],
        region_codes: list[str],
    ) -> dict[int, HierarchyItem]:
        hierarchy: dict[int, HierarchyItem] = {}
        hierarchy_files = [
            path for path in xml_files
            if classify_xml_file(path) == "hierarchy"
        ]

        for path in hierarchy_files:
            for _event, elem in iterparse(path, events=("end",)):
                if local_tag(elem.tag) not in HIERARCHY_TAGS:
                    elem.clear()
                    continue

                attrs = elem_attrs(elem)
                object_id = safe_int(first_attr(attrs, "OBJECTID", "OBJID", "ID"))
                if object_id is None:
                    elem.clear()
                    continue

                region_code = first_attr(attrs, "REGIONCODE", "REGION_CODE")
                if region_codes and region_code and region_code not in region_codes:
                    elem.clear()
                    continue

                hierarchy[object_id] = HierarchyItem(
                    object_id=object_id,
                    parent_object_id=safe_int(
                        first_attr(attrs, "PARENTOBJID", "PARENTOBJECTID", "PARENTID")
                    ),
                    region_code=region_code,
                    path=first_attr(attrs, "PATH"),
                    is_active=safe_bool(first_attr(attrs, "ISACTIVE"), default=True),
                )
                elem.clear()

        return hierarchy

    async def _upsert_regions(self, region_codes: list[str]) -> None:
        rows = [
            {
                "gar_id": None,
                "region_code": code,
                "name": REGION_LABELS.get(code, (code, None))[0],
                "short_name": REGION_LABELS.get(code, (code, None))[1],
                "is_actual": True,
            }
            for code in region_codes
        ]
        if not rows:
            return

        await self.db.execute(
            text(
                """
                INSERT INTO gar_regions (
                    gar_id,
                    region_code,
                    name,
                    short_name,
                    is_actual
                )
                VALUES (
                    :gar_id,
                    :region_code,
                    :name,
                    :short_name,
                    :is_actual
                )
                ON CONFLICT (region_code)
                DO UPDATE SET
                    gar_id = COALESCE(EXCLUDED.gar_id, gar_regions.gar_id),
                    name = EXCLUDED.name,
                    short_name = EXCLUDED.short_name,
                    is_actual = EXCLUDED.is_actual
                """
            ),
            rows,
        )
        await self.db.commit()

    async def _import_objects_file(
        self,
        path: Path,
        *,
        hierarchy: dict[int, HierarchyItem],
        region_codes: list[str],
    ) -> int:
        imported = 0
        batch: list[dict[str, Any]] = []

        for _event, elem in iterparse(path, events=("end",)):
            if local_tag(elem.tag) not in ADDRESS_OBJECT_TAGS:
                elem.clear()
                continue

            row = self._object_row(elem_attrs(elem), hierarchy)
            elem.clear()
            if row is None:
                continue
            if region_codes and row["region_code"] and row["region_code"] not in region_codes:
                continue

            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                imported += await self._flush_objects(batch)
                batch.clear()

        if batch:
            imported += await self._flush_objects(batch)

        return imported

    def _object_row(
        self,
        attrs: dict[str, str],
        hierarchy: dict[int, HierarchyItem],
    ) -> dict[str, Any] | None:
        object_id = safe_int(first_attr(attrs, "OBJECTID", "OBJID", "ID"))
        name = first_attr(attrs, "NAME", "FORMALNAME", "OFFNAME")
        if object_id is None or not name:
            return None

        hierarchy_item = hierarchy.get(object_id)
        type_name = normalize_type_name(
            first_attr(attrs, "TYPENAME", "SHORTNAME", "TYPESHORTNAME")
        )
        return {
            "gar_id": first_attr(attrs, "OBJECTGUID", "AOGUID", "AOID", "GUID"),
            "object_id": object_id,
            "parent_object_id": (
                hierarchy_item.parent_object_id
                if hierarchy_item is not None
                else safe_int(first_attr(attrs, "PARENTOBJID", "PARENTID"))
            ),
            "object_level": safe_int(first_attr(attrs, "LEVEL", "OBJECTLEVEL")),
            "name": name.strip(),
            "type_name": type_name,
            "full_name": full_object_name(name, type_name),
            "region_code": (
                first_attr(attrs, "REGIONCODE", "REGION_CODE")
                or (hierarchy_item.region_code if hierarchy_item is not None else None)
            ),
            "is_actual": safe_bool(first_attr(attrs, "ISACTUAL"), default=True),
            "is_active": (
                hierarchy_item.is_active
                if hierarchy_item is not None
                else safe_bool(first_attr(attrs, "ISACTIVE"), default=True)
            ),
            "path": hierarchy_item.path if hierarchy_item is not None else None,
        }

    async def _flush_objects(self, rows: list[dict[str, Any]]) -> int:
        await self.db.execute(
            text(
                """
                INSERT INTO gar_address_objects (
                    gar_id,
                    object_id,
                    parent_object_id,
                    object_level,
                    name,
                    type_name,
                    full_name,
                    region_code,
                    is_actual,
                    is_active,
                    path
                )
                VALUES (
                    :gar_id,
                    :object_id,
                    :parent_object_id,
                    :object_level,
                    :name,
                    :type_name,
                    :full_name,
                    :region_code,
                    :is_actual,
                    :is_active,
                    :path
                )
                ON CONFLICT (object_id)
                DO UPDATE SET
                    gar_id = EXCLUDED.gar_id,
                    parent_object_id = EXCLUDED.parent_object_id,
                    object_level = EXCLUDED.object_level,
                    name = EXCLUDED.name,
                    type_name = EXCLUDED.type_name,
                    full_name = EXCLUDED.full_name,
                    region_code = EXCLUDED.region_code,
                    is_actual = EXCLUDED.is_actual,
                    is_active = EXCLUDED.is_active,
                    path = EXCLUDED.path
                """
            ),
            rows,
        )
        await self.db.commit()
        return len(rows)

    async def _import_houses_file(
        self,
        path: Path,
        *,
        hierarchy: dict[int, HierarchyItem],
        region_codes: list[str],
    ) -> int:
        imported = 0
        batch: list[dict[str, Any]] = []

        for _event, elem in iterparse(path, events=("end",)):
            if local_tag(elem.tag) not in HOUSE_TAGS:
                elem.clear()
                continue

            row = self._house_row(elem_attrs(elem), hierarchy)
            elem.clear()
            if row is None:
                continue
            if region_codes and row["region_code"] and row["region_code"] not in region_codes:
                continue

            batch.append(row)
            if len(batch) >= BATCH_SIZE:
                imported += await self._flush_houses(batch)
                batch.clear()

        if batch:
            imported += await self._flush_houses(batch)

        return imported

    def _house_row(
        self,
        attrs: dict[str, str],
        hierarchy: dict[int, HierarchyItem],
    ) -> dict[str, Any] | None:
        object_id = safe_int(first_attr(attrs, "OBJECTID", "OBJID"))
        house_id = safe_int(first_attr(attrs, "HOUSEID", "ID")) or object_id
        if house_id is None:
            return None

        hierarchy_item = hierarchy.get(object_id) if object_id is not None else None
        return {
            "gar_id": first_attr(attrs, "OBJECTGUID", "HOUSEGUID", "AOGUID", "GUID"),
            "object_id": object_id,
            "house_id": house_id,
            "parent_object_id": (
                hierarchy_item.parent_object_id
                if hierarchy_item is not None
                else safe_int(first_attr(attrs, "PARENTOBJID", "PARENTID"))
            ),
            "house_number": first_attr(attrs, "HOUSENUM", "HOUSENUMBER", "HOUSE_NUM"),
            "building_number": first_attr(attrs, "ADDNUM1", "BUILDNUM", "BUILDINGNUM"),
            "structure_number": first_attr(attrs, "ADDNUM2", "STRUCNUM", "STRUCTURENUM"),
            "house_type": first_attr(attrs, "HOUSETYPE", "HOUSE_TYPE"),
            "building_type": first_attr(attrs, "ADDTYPE1", "BUILDTYPE"),
            "structure_type": first_attr(attrs, "ADDTYPE2", "STRUCTYPE"),
            "postcode": first_attr(attrs, "POSTALCODE", "POSTCODE"),
            "region_code": (
                first_attr(attrs, "REGIONCODE", "REGION_CODE")
                or (hierarchy_item.region_code if hierarchy_item is not None else None)
            ),
            "is_actual": safe_bool(first_attr(attrs, "ISACTUAL"), default=True),
            "is_active": (
                hierarchy_item.is_active
                if hierarchy_item is not None
                else safe_bool(first_attr(attrs, "ISACTIVE"), default=True)
            ),
        }

    async def _flush_houses(self, rows: list[dict[str, Any]]) -> int:
        await self.db.execute(
            text(
                """
                INSERT INTO gar_houses (
                    gar_id,
                    object_id,
                    house_id,
                    parent_object_id,
                    house_number,
                    building_number,
                    structure_number,
                    house_type,
                    building_type,
                    structure_type,
                    postcode,
                    region_code,
                    is_actual,
                    is_active
                )
                VALUES (
                    :gar_id,
                    :object_id,
                    :house_id,
                    :parent_object_id,
                    :house_number,
                    :building_number,
                    :structure_number,
                    :house_type,
                    :building_type,
                    :structure_type,
                    :postcode,
                    :region_code,
                    :is_actual,
                    :is_active
                )
                ON CONFLICT (house_id)
                DO UPDATE SET
                    gar_id = EXCLUDED.gar_id,
                    object_id = EXCLUDED.object_id,
                    parent_object_id = EXCLUDED.parent_object_id,
                    house_number = EXCLUDED.house_number,
                    building_number = EXCLUDED.building_number,
                    structure_number = EXCLUDED.structure_number,
                    house_type = EXCLUDED.house_type,
                    building_type = EXCLUDED.building_type,
                    structure_type = EXCLUDED.structure_type,
                    postcode = EXCLUDED.postcode,
                    region_code = EXCLUDED.region_code,
                    is_actual = EXCLUDED.is_actual,
                    is_active = EXCLUDED.is_active
                """
            ),
            rows,
        )
        await self.db.commit()
        return len(rows)

    async def _mark_run(self, import_id: int, *, status: str) -> None:
        await self.db.execute(
            text(
                """
                UPDATE gar_import_runs
                SET status = :status
                WHERE id = :import_id
                """
            ),
            {"import_id": import_id, "status": status},
        )
        await self.db.commit()

    async def _finish_run(
        self,
        import_id: int,
        *,
        status: str,
        stats: GarImportStats,
        error_message: str | None = None,
    ) -> None:
        report = stats.to_report()
        await self.db.execute(
            text(
                """
                UPDATE gar_import_runs
                SET
                    status = :status,
                    address_objects_imported = :address_objects_imported,
                    houses_imported = :houses_imported,
                    updated = :updated,
                    skipped = :skipped,
                    errors = :errors,
                    error_message = :error_message,
                    report = CAST(:report AS jsonb),
                    finished_at = now()
                WHERE id = :import_id
                """
            ),
            {
                "import_id": import_id,
                "status": status,
                "address_objects_imported": stats.address_objects_imported,
                "houses_imported": stats.houses_imported,
                "updated": stats.updated,
                "skipped": stats.skipped,
                "errors": stats.errors,
                "error_message": error_message,
                "report": json.dumps(report, ensure_ascii=False),
            },
        )
        await self.db.commit()
