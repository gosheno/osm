from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import AsyncSessionLocal, get_db
from app.schemas.gar import (
    GarImportRequest,
    GarImportResponse,
    GarImportStatusResponse,
)
from app.services.gar_importer import GarImportService


router = APIRouter(prefix="/api/gar", tags=["gar"])


@router.post("/import", response_model=GarImportResponse)
async def import_gar(
    payload: GarImportRequest,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    service = GarImportService(db)
    import_id = await service.create_import_run(
        region=payload.region,
        source_path=payload.path,
    )
    background_tasks.add_task(
        run_gar_import,
        import_id,
        payload.region,
        payload.path,
    )
    return GarImportResponse(status="pending", import_id=import_id)


@router.get("/import/{import_id}", response_model=GarImportStatusResponse)
async def get_gar_import(
    import_id: int,
    db: AsyncSession = Depends(get_db),
):
    row = await GarImportService(db).get_import_run(import_id)
    if row is None:
        raise HTTPException(status_code=404, detail=f"GAR import {import_id} not found.")
    return GarImportStatusResponse(**row)


async def run_gar_import(import_id: int, region: str, source_path: str) -> None:
    async with AsyncSessionLocal() as session:
        await GarImportService(session).import_path(
            import_id=import_id,
            region=region,
            source_path=source_path,
        )
