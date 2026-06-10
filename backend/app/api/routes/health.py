from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

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
