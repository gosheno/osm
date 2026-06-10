from typing import Literal

from pydantic import BaseModel, Field


RoutePointType = Literal["start", "waypoint", "end"]


class YandexLinkPointInput(BaseModel):
    batch_order: int = Field(..., ge=0)
    global_order: int = Field(..., ge=0)
    type: RoutePointType
    label: str | None = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    original_index: int = Field(..., ge=0)
    is_transition_point: bool = False


class YandexLinkBatchInput(BaseModel):
    batch_number: int | None = Field(default=None, ge=1)
    points: list[YandexLinkPointInput] = Field(default_factory=list)


class BuildYandexLinksRequest(BaseModel):
    city_slug: str = "saint-petersburg"
    route_type: str = "auto"
    round_coordinates: int = Field(default=6, ge=0, le=8)
    max_url_length: int = Field(default=2000, ge=1)
    batches: list[YandexLinkBatchInput] = Field(default_factory=list)


class YandexLinkBatchResponse(BaseModel):
    batch_number: int
    points_count: int
    url_length: int
    has_warning: bool
    warnings: list[str]
    yandex_maps_url: str
    points: list[YandexLinkPointInput]


class BuildYandexLinksResponse(BaseModel):
    status: Literal["completed", "completed_with_warnings", "failed"]
    city_slug: str
    route_type: str
    batches_count: int
    batches: list[YandexLinkBatchResponse]
