from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppError
from app.db.session import get_db
from app.schemas.imports import (
    RouteImportConfirmRequest,
    RouteImportConfirmResponse,
    RouteImportCreateResponse,
    RouteImportItemPatchRequest,
    RouteImportRead,
)
from app.services.ocr_service import OcrServiceError
from app.services.route_import_service import RouteImportError, RouteImportService


router = APIRouter(prefix="/api/imports", tags=["imports"])


@router.post("/route-sheet", response_model=RouteImportCreateResponse)
async def upload_route_sheet(
    files: list[UploadFile] = File(...),
    db: AsyncSession = Depends(get_db),
):
    try:
        service = RouteImportService(db)
        result = await service.create_from_uploads(files)
        return RouteImportCreateResponse(
            import_id=result["import_id"],
            status=result["status"],
        )
    except RouteImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OcrServiceError as exc:
        raise AppError(
            code="OCR_SERVICE_UNAVAILABLE",
            message="OCR service is unavailable.",
            details=str(exc),
            status_code=503,
        )
    except Exception as exc:
        raise AppError(
            code="ROUTE_IMPORT_FAILED",
            message="Route sheet import failed.",
            details=str(exc),
            status_code=503,
        )


@router.post("/route-sheet/from-local", response_model=RouteImportRead)
async def import_local_route_sheet(
    route_name: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = RouteImportService(db)
        return await service.create_from_local_directory(route_name)
    except RouteImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OcrServiceError as exc:
        raise AppError(
            code="OCR_SERVICE_UNAVAILABLE",
            message="OCR service is unavailable.",
            details=str(exc),
            status_code=503,
        )
    except Exception as exc:
        raise AppError(
            code="ROUTE_IMPORT_FAILED",
            message="Local route sheet import failed.",
            details=str(exc),
            status_code=503,
        )


@router.get("/{import_id}", response_model=RouteImportRead)
async def get_route_import(
    import_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = RouteImportService(db)
        return await service.get_import(import_id)
    except RouteImportError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.patch("/{import_id}/items/{item_id}", response_model=RouteImportRead)
async def patch_route_import_item(
    import_id: int,
    item_id: int,
    payload: RouteImportItemPatchRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = RouteImportService(db)
        return await service.patch_item(
            import_id=import_id,
            item_id=item_id,
            store_name=payload.store_name,
            address=payload.address,
            status=payload.status,
        )
    except RouteImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{import_id}/items/{item_id}/retry-geocode", response_model=RouteImportRead)
async def retry_route_import_item_geocode(
    import_id: int,
    item_id: int,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = RouteImportService(db)
        return await service.retry_geocode(import_id=import_id, item_id=item_id)
    except RouteImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/{import_id}/confirm", response_model=RouteImportConfirmResponse)
async def confirm_route_import(
    import_id: int,
    payload: RouteImportConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = RouteImportService(db)
        return await service.confirm_import(import_id, payload)
    except RouteImportError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
