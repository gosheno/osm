from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.nominatim_client import NominatimClient
from app.core.config import settings
from app.db.session import get_db


router = APIRouter(prefix="/api", tags=["health"])


@router.get("/health/db")
async def health_db(db: AsyncSession = Depends(get_db)):
    try:
        result = await db.execute(
            text("SELECT 1 AS ok, PostGIS_Version() AS postgis_version")
        )
        row = result.mappings().one()

        return {
            "status": "ok",
            "service": "database",
            "db_check": row["ok"],
            "postgis_version": row["postgis_version"],
        }
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Database is not available: {exc}",
        )


@router.get("/health/nominatim")
async def health_nominatim():
    client = NominatimClient()
    result = await client.health_check()

    payload = {
        "status": "ok" if result.available else "unavailable",
        "service": "nominatim",
        "provider": "nominatim",
        "url": settings.NOMINATIM_BASE_URL,
        "status_code": result.status_code,
        "response_time_ms": result.response_time_ms,
        "body": result.body,
    }

    if not result.available:
        payload["error"] = result.error
        raise HTTPException(status_code=503, detail=payload)

    return payload
