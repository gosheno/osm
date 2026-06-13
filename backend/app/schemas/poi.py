from __future__ import annotations

from pydantic import BaseModel, Field


class PoiSearchItem(BaseModel):
    id: int
    canonical_brand: str
    name: str | None = None
    address: str | None = None
    latitude: float
    longitude: float
    confidence_score: float | None = None
    distance_m: float | None = None
    osm_type: str | None = None
    osm_id: int | None = None
    source: str = "known_pois"


class PoiSearchResponse(BaseModel):
    items: list[PoiSearchItem] = Field(default_factory=list)

