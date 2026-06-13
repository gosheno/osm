from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.poi import PoiSearchResponse
from app.services.poi_matcher import PoiMatcher, poi_candidate_to_api


router = APIRouter(prefix="/api/pois", tags=["pois"])


@router.get("/search", response_model=PoiSearchResponse)
async def search_pois(
    q: str = "",
    brand: str | None = None,
    lat: float | None = None,
    lon: float | None = None,
    radius_m: int | None = None,
    limit: int = 10,
    db: AsyncSession = Depends(get_db),
):
    try:
        matcher = PoiMatcher(db)
        items = await matcher.find_candidates(
            text_value=q,
            brand=brand,
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            limit=limit,
        )
        if radius_m is not None:
            items = [
                item for item in items
                if item.distance_m is None or item.distance_m <= radius_m
            ]
        return PoiSearchResponse(items=[poi_candidate_to_api(item) for item in items])
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"POI search failed: {exc}")
