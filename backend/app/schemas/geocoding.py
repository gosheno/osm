from typing import Literal

from pydantic import BaseModel, Field


GeocodingContextType = Literal[
    "default_spb",
    "spb_lenobl",
    "district",
    "custom_area",
]


class GeocodingContextInput(BaseModel):
    type: GeocodingContextType | None = None
    label: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    radius_km: float | None = Field(default=None, gt=0, le=500)
    source: str | None = None
    bounded: bool = False
