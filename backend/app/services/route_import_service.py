from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from fastapi import UploadFile
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.schemas.geocoding import GeocodingContextInput
from app.schemas.imports import RouteImportConfirmRequest
from app.schemas.route import OptimizeRouteByAddressesRequest, SelectedRouteAddress
from app.services.address_service import AddressService
from app.services.image_preprocessing import SUPPORTED_IMAGE_SUFFIXES, preprocess_image
from app.services.ocr_service import OcrServiceClient, OcrServiceError, OcrResult
from app.services.route_pipeline import optimize_route_by_addresses
from app.services.route_sheet_parser import ParsedRouteSheetRow, RouteSheetParser
from app.utils.address_normalizer import normalize_address


class RouteImportError(Exception):
    pass


class RouteImportService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.ocr = OcrServiceClient()
        self.parser = RouteSheetParser()

    async def create_from_uploads(self, files: list[UploadFile]) -> dict[str, Any]:
        if not files:
            raise RouteImportError("Upload at least one route sheet image.")
        if len(files) > settings.OCR_MAX_FILES:
            raise RouteImportError(f"Too many files. Maximum: {settings.OCR_MAX_FILES}.")

        import_id = await self._create_import()
        upload_dir = self._import_dir(import_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        for image_order, file in enumerate(files, start=1):
            await self._save_upload(import_id, upload_dir, image_order, file)

        await self.process_import(import_id)
        return await self.get_import(import_id)

    async def create_from_local_directory(self, route_name: str | None = None) -> dict[str, Any]:
        base_dir = Path(settings.OCR_SAMPLE_ROUTES_DIR)
        source_dir = base_dir / route_name if route_name else self._latest_sample_dir(base_dir)
        if not source_dir.exists() or not source_dir.is_dir():
            raise RouteImportError(f"Sample route directory not found: {source_dir}")

        image_paths = [
            path for path in sorted(source_dir.iterdir())
            if path.suffix.lower() in SUPPORTED_IMAGE_SUFFIXES and path.is_file()
        ]
        if not image_paths:
            raise RouteImportError(f"No sample images found in {source_dir}")

        import_id = await self._create_import(source_type="sample_route")
        upload_dir = self._import_dir(import_id)
        upload_dir.mkdir(parents=True, exist_ok=True)

        for image_order, source_path in enumerate(image_paths, start=1):
            target_path = upload_dir / f"{image_order:03d}-{source_path.name}"
            shutil.copy2(source_path, target_path)
            await self._insert_image(
                import_id=import_id,
                file_path=target_path,
                original_filename=str(source_path.relative_to(base_dir)),
                image_order=image_order,
            )

        await self.process_import(import_id)
        return await self.get_import(import_id)

    async def process_import(self, import_id: int) -> None:
        await self._set_import_status(import_id, "processing")
        images = await self._images(import_id)
        raw_texts: list[str] = []
        ocr_engines: set[str] = set()
        row_offset = 0

        try:
            for image in images:
                image_id = int(image["id"])
                source_path = Path(image["file_path"])
                preprocessed_path = source_path.with_name(f"{source_path.stem}.preprocessed.png")
                try:
                    preprocess_image(source_path, preprocessed_path)
                    await self._update_image(
                        image_id,
                        ocr_status="preprocessed",
                        preprocessed_file_path=preprocessed_path,
                    )
                    ocr_result = await self._recognize_best_image(
                        source_path=source_path,
                        preprocessed_path=preprocessed_path,
                    )
                    ocr_engines.add(ocr_result.engine)
                    raw_texts.append(ocr_result.raw_text)
                    await self._update_image(image_id, ocr_status="recognized")
                    rows = await self._store_parsed_rows(
                        import_id=import_id,
                        source_image_id=image_id,
                        ocr_result=ocr_result,
                        row_offset=row_offset,
                    )
                    row_offset += len(rows)
                except OcrServiceError as exc:
                    await self._update_image(image_id, ocr_status="failed", error_message=str(exc))
                    raise

            await self._mark_duplicates(import_id)
            await self._set_import_status(
                import_id,
                "completed",
                raw_text="\n\n".join(raw_texts),
                ocr_engine=", ".join(sorted(ocr_engines)) if ocr_engines else None,
            )
        except Exception as exc:
            await self._set_import_status(import_id, "failed", error_message=str(exc))
            raise

    async def _recognize_best_image(self, *, source_path: Path, preprocessed_path: Path) -> OcrResult:
        preprocessed_result = await self.ocr.recognize_image(preprocessed_path)
        preprocessed_rows = self.parser.parse(preprocessed_result)

        should_try_original = (
            len(preprocessed_rows) < 10
            or len(preprocessed_result.raw_text or "") < 800
            or preprocessed_result.engine == "tesseract"
        )
        if not should_try_original:
            return preprocessed_result

        original_result = await self.ocr.recognize_image(source_path)
        original_rows = self.parser.parse(original_result)

        preprocessed_score = (len(preprocessed_rows), len(preprocessed_result.raw_text or ""))
        original_score = (len(original_rows), len(original_result.raw_text or ""))
        return original_result if original_score > preprocessed_score else preprocessed_result

    async def get_import(self, import_id: int) -> dict[str, Any]:
        import_row = await self._import_row(import_id)
        if import_row is None:
            raise RouteImportError(f"Import {import_id} not found.")

        return {
            "import_id": import_row["id"],
            "status": import_row["status"],
            "source_type": import_row["source_type"],
            "ocr_engine": import_row["ocr_engine"],
            "raw_text": import_row["raw_text"],
            "error_message": import_row["error_message"],
            "images": await self._images(import_id),
            "items": await self._items(import_id),
        }

    async def patch_item(
        self,
        *,
        import_id: int,
        item_id: int,
        store_name: str | None = None,
        address: str | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        item = await self._item(import_id, item_id)
        if item is None:
            raise RouteImportError(f"Item {item_id} not found.")

        corrected_address = address.strip() if address is not None else None
        normalized_address = None
        if corrected_address:
            normalized_address = normalize_address(
                corrected_address,
                default_city=settings.DEFAULT_CITY,
            ).normalized_address

        await self.db.execute(
            text(
                """
                UPDATE route_import_items
                SET
                    user_corrected_store_name = COALESCE(:store_name, user_corrected_store_name),
                    user_corrected_address = COALESCE(:address, user_corrected_address),
                    store_name = COALESCE(:store_name, store_name),
                    address = COALESCE(:address, address),
                    normalized_address = COALESCE(:normalized_address, normalized_address),
                    status = COALESCE(:status, status),
                    geocoding_status = CASE WHEN :address IS NULL THEN geocoding_status ELSE 'pending' END,
                    address_id = CASE WHEN :address IS NULL THEN address_id ELSE NULL END,
                    error_message = NULL
                WHERE import_id = :import_id AND id = :item_id
                """
            ),
            {
                "store_name": store_name.strip() if store_name is not None else None,
                "address": corrected_address,
                "normalized_address": normalized_address,
                "status": status,
                "import_id": import_id,
                "item_id": item_id,
            },
        )
        await self.db.commit()
        return await self.get_import(import_id)

    async def retry_geocode(self, *, import_id: int, item_id: int) -> dict[str, Any]:
        item = await self._item(import_id, item_id)
        if item is None:
            raise RouteImportError(f"Item {item_id} not found.")
        await self._geocode_item(item)
        await self._mark_duplicates(import_id)
        return await self.get_import(import_id)

    async def confirm_import(
        self,
        import_id: int,
        payload: RouteImportConfirmRequest,
    ) -> dict[str, Any]:
        items = await self._items(import_id)
        include_ids = set(payload.include_item_ids or [item["id"] for item in items])
        included = [
            item for item in items
            if item["id"] in include_ids and item["status"] not in {"rejected", "duplicate"}
        ]
        problematic = [
            item for item in included
            if item["address_id"] is None or item["geocoding_status"] != "found"
        ]

        if problematic and not payload.exclude_problematic:
            raise RouteImportError(
                "Some imported records are not geocoded. Fix them or choose to exclude problematic rows."
            )

        valid_items = [
            item for item in included
            if item["address_id"] is not None and item["geocoding_status"] == "found"
        ]
        if not valid_items:
            raise RouteImportError("No confirmed geocoded rows are available for route building.")

        selected_waypoints = await self._selected_waypoints(valid_items)
        route_payload = OptimizeRouteByAddressesRequest(
            start_address=payload.start_address,
            end_address=payload.end_address,
            addresses=[item["user_corrected_address"] or item["address"] for item in valid_items],
            waypoints_selected=selected_waypoints,
            batch_size=payload.batch_size,
            optimization_metric=payload.optimization_metric,
            city_slug=payload.city_slug,
            default_city=payload.default_city,
            geocoding_context={"type": "spb_lenobl", "bounded": False},
        )
        route = await optimize_route_by_addresses(route_payload, self.db)

        await self.db.execute(
            text(
                """
                UPDATE route_import_items
                SET status = 'confirmed'
                WHERE import_id = :import_id AND id = ANY(:item_ids)
                """
            ),
            {"import_id": import_id, "item_ids": [item["id"] for item in valid_items]},
        )
        await self._set_import_status(import_id, "confirmed")

        return {
            "route_job_id": route.route_job_id,
            "status": "created",
            "included_item_ids": [item["id"] for item in valid_items],
            "excluded_item_ids": [item["id"] for item in items if item not in valid_items],
            "route": route,
        }

    async def _create_import(self, source_type: str = "route_sheet") -> int:
        result = await self.db.execute(
            text(
                """
                INSERT INTO route_imports (status, source_type, ocr_engine)
                VALUES ('uploaded', :source_type, :ocr_engine)
                RETURNING id
                """
            ),
            {"source_type": source_type, "ocr_engine": settings.OCR_ENGINE},
        )
        import_id = int(result.scalar_one())
        await self.db.commit()
        return import_id

    async def _save_upload(
        self,
        import_id: int,
        upload_dir: Path,
        image_order: int,
        file: UploadFile,
    ) -> None:
        suffix = Path(file.filename or "").suffix.lower()
        if suffix not in SUPPORTED_IMAGE_SUFFIXES:
            raise RouteImportError(f"Unsupported file format: {file.filename}")

        target_path = upload_dir / f"{image_order:03d}-{Path(file.filename or 'image').name}"
        content = await file.read()
        max_size = settings.OCR_MAX_FILE_SIZE_MB * 1024 * 1024
        if len(content) > max_size:
            raise RouteImportError(f"File is too large: {file.filename}")
        target_path.write_bytes(content)

        await self._insert_image(
            import_id=import_id,
            file_path=target_path,
            original_filename=file.filename or target_path.name,
            image_order=image_order,
        )

    async def _insert_image(
        self,
        *,
        import_id: int,
        file_path: Path,
        original_filename: str,
        image_order: int,
    ) -> int:
        result = await self.db.execute(
            text(
                """
                INSERT INTO route_import_images (
                    import_id, file_path, original_filename, image_order, ocr_status
                )
                VALUES (:import_id, :file_path, :original_filename, :image_order, 'uploaded')
                RETURNING id
                """
            ),
            {
                "import_id": import_id,
                "file_path": str(file_path),
                "original_filename": original_filename,
                "image_order": image_order,
            },
        )
        image_id = int(result.scalar_one())
        await self.db.commit()
        return image_id

    async def _store_parsed_rows(
        self,
        *,
        import_id: int,
        source_image_id: int,
        ocr_result: OcrResult,
        row_offset: int,
    ) -> list[ParsedRouteSheetRow]:
        rows = self.parser.parse(ocr_result, row_offset=row_offset)
        for row in rows:
            normalized = normalize_address(
                row.address,
                default_city=settings.DEFAULT_CITY,
            )
            result = await self.db.execute(
                text(
                    """
                    INSERT INTO route_import_items (
                        import_id,
                        source_image_id,
                        row_number,
                        raw_ocr_text,
                        store_name,
                        address,
                        normalized_address,
                        confidence_score,
                        status
                    )
                    VALUES (
                        :import_id,
                        :source_image_id,
                        :row_number,
                        :raw_ocr_text,
                        :store_name,
                        :address,
                        :normalized_address,
                        :confidence_score,
                        'recognized'
                    )
                    RETURNING *
                    """
                ),
                {
                    "import_id": import_id,
                    "source_image_id": source_image_id,
                    "row_number": row.row_number,
                    "raw_ocr_text": row.raw_ocr_text,
                    "store_name": row.store_name,
                    "address": row.address,
                    "normalized_address": normalized.normalized_address,
                    "confidence_score": row.confidence_score,
                },
            )
            inserted = dict(result.mappings().one())
            await self.db.commit()
            await self._geocode_item(inserted)
        return rows

    async def _geocode_item(self, item: dict[str, Any]) -> None:
        address = item.get("user_corrected_address") or item.get("address")
        if not address:
            await self._update_item_geocode(
                item["id"],
                status="needs_review",
                geocoding_status="not_found",
                error_message="No address text was extracted.",
            )
            return

        service = AddressService(self.db)
        try:
            result = await service.geocode_address(
                address,
                default_city=settings.DEFAULT_CITY,
                geocoding_context=GeocodingContextInput(type="spb_lenobl", bounded=False),
            )
        except Exception as exc:
            await self._update_item_geocode(
                item["id"],
                status="needs_review",
                geocoding_status="error",
                error_message=str(exc),
            )
            return

        address_id = result.get("id")
        geocoding_status = result.get("geocoding_status")
        confidence = _combined_confidence(
            item.get("confidence_score"),
            result.get("geocoding_score") or result.get("confidence_score"),
        )
        item_status = (
            "recognized"
            if geocoding_status == "found" and confidence >= 0.85
            else "needs_review"
        )
        await self._update_item_geocode(
            item["id"],
            status=item_status,
            geocoding_status=geocoding_status,
            address_id=address_id,
            confidence_score=confidence,
            normalized_address=result.get("normalized_address"),
            error_message=result.get("error"),
        )

    async def _update_item_geocode(
        self,
        item_id: int,
        *,
        status: str,
        geocoding_status: str | None,
        address_id: int | None = None,
        confidence_score: float | None = None,
        normalized_address: str | None = None,
        error_message: str | None = None,
    ) -> None:
        await self.db.execute(
            text(
                """
                UPDATE route_import_items
                SET
                    status = :status,
                    geocoding_status = :geocoding_status,
                    address_id = :address_id,
                    confidence_score = COALESCE(:confidence_score, confidence_score),
                    normalized_address = COALESCE(:normalized_address, normalized_address),
                    error_message = :error_message
                WHERE id = :item_id
                """
            ),
            {
                "item_id": item_id,
                "status": status,
                "geocoding_status": geocoding_status,
                "address_id": address_id,
                "confidence_score": confidence_score,
                "normalized_address": normalized_address,
                "error_message": error_message,
            },
        )
        await self.db.commit()

    async def _mark_duplicates(self, import_id: int) -> None:
        items = await self._items(import_id)
        seen: dict[str, int] = {}
        for item in items:
            key = (item.get("normalized_address") or "").strip().lower()
            if not key:
                continue
            if key in seen:
                await self.db.execute(
                    text(
                        """
                        UPDATE route_import_items
                        SET status = 'duplicate', possible_duplicate_of_id = :duplicate_of
                        WHERE id = :item_id AND status != 'rejected'
                        """
                    ),
                    {"item_id": item["id"], "duplicate_of": seen[key]},
                )
            else:
                seen[key] = item["id"]
        await self.db.commit()

    async def _selected_waypoints(self, items: list[dict[str, Any]]) -> list[SelectedRouteAddress | None]:
        if not items:
            return []
        result = await self.db.execute(
            text(
                """
                SELECT id, display_name, original_address, latitude, longitude, confidence_score, geocoding_status
                FROM addresses
                WHERE id = ANY(:ids)
                """
            ),
            {"ids": [item["address_id"] for item in items]},
        )
        rows = {row["id"]: row for row in result.mappings().all()}
        selected: list[SelectedRouteAddress | None] = []
        for item in items:
            row = rows.get(item["address_id"])
            if row is None or row["latitude"] is None or row["longitude"] is None:
                selected.append(None)
                continue
            selected.append(
                SelectedRouteAddress(
                    address_id=row["id"],
                    display_name=(
                        item.get("user_corrected_address")
                        or item.get("address")
                        or row.get("display_name")
                        or row.get("original_address")
                    ),
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    confidence_score=(
                        float(row["confidence_score"])
                        if row["confidence_score"] is not None
                        else None
                    ),
                    geocoding_status=row["geocoding_status"] or "found",
                )
            )
        return selected

    async def _set_import_status(
        self,
        import_id: int,
        status: str,
        *,
        raw_text: str | None = None,
        error_message: str | None = None,
        ocr_engine: str | None = None,
    ) -> None:
        await self.db.execute(
            text(
                """
                UPDATE route_imports
                SET
                    status = :status,
                    raw_text = COALESCE(:raw_text, raw_text),
                    ocr_engine = COALESCE(:ocr_engine, ocr_engine),
                    error_message = :error_message
                WHERE id = :import_id
                """
            ),
            {
                "import_id": import_id,
                "status": status,
                "raw_text": raw_text,
                "error_message": error_message,
                "ocr_engine": ocr_engine,
            },
        )
        await self.db.commit()

    async def _update_image(
        self,
        image_id: int,
        *,
        ocr_status: str,
        preprocessed_file_path: Path | None = None,
        error_message: str | None = None,
    ) -> None:
        await self.db.execute(
            text(
                """
                UPDATE route_import_images
                SET
                    ocr_status = :ocr_status,
                    preprocessed_file_path = COALESCE(:preprocessed_file_path, preprocessed_file_path),
                    error_message = :error_message
                WHERE id = :image_id
                """
            ),
            {
                "image_id": image_id,
                "ocr_status": ocr_status,
                "preprocessed_file_path": str(preprocessed_file_path) if preprocessed_file_path else None,
                "error_message": error_message,
            },
        )
        await self.db.commit()

    async def _import_row(self, import_id: int) -> dict[str, Any] | None:
        result = await self.db.execute(
            text("SELECT * FROM route_imports WHERE id = :import_id"),
            {"import_id": import_id},
        )
        row = result.mappings().one_or_none()
        return dict(row) if row else None

    async def _images(self, import_id: int) -> list[dict[str, Any]]:
        result = await self.db.execute(
            text(
                """
                SELECT *
                FROM route_import_images
                WHERE import_id = :import_id
                ORDER BY image_order, id
                """
            ),
            {"import_id": import_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def _items(self, import_id: int) -> list[dict[str, Any]]:
        result = await self.db.execute(
            text(
                """
                SELECT *
                FROM route_import_items
                WHERE import_id = :import_id
                ORDER BY row_number, id
                """
            ),
            {"import_id": import_id},
        )
        return [dict(row) for row in result.mappings().all()]

    async def _item(self, import_id: int, item_id: int) -> dict[str, Any] | None:
        result = await self.db.execute(
            text(
                """
                SELECT *
                FROM route_import_items
                WHERE import_id = :import_id AND id = :item_id
                """
            ),
            {"import_id": import_id, "item_id": item_id},
        )
        row = result.mappings().one_or_none()
        return dict(row) if row else None

    def _import_dir(self, import_id: int) -> Path:
        return Path(settings.OCR_UPLOAD_DIR) / str(import_id)

    def _latest_sample_dir(self, base_dir: Path) -> Path:
        candidates = [path for path in base_dir.iterdir() if path.is_dir()]
        if not candidates:
            raise RouteImportError(f"No sample route directories found in {base_dir}")
        return max(candidates, key=lambda path: path.stat().st_mtime)


def _combined_confidence(ocr_confidence: Any, geocoding_confidence: Any) -> float:
    try:
        ocr = float(ocr_confidence) if ocr_confidence is not None else 0.6
    except (TypeError, ValueError):
        ocr = 0.6
    try:
        geocoding = float(geocoding_confidence) if geocoding_confidence is not None else 50.0
    except (TypeError, ValueError):
        geocoding = 50.0

    if geocoding > 1:
        geocoding = geocoding / 100
    return round(max(0.0, min((ocr * 0.45) + (geocoding * 0.55), 0.99)), 2)
