from typing import Literal

from pydantic import BaseModel, Field


RoutePointType = Literal["start", "waypoint", "end"]


class BatchPointInput(BaseModel):
    order: int = Field(..., ge=0)
    type: RoutePointType
    label: str | None = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    original_index: int = Field(..., ge=0)


class RouteLegInput(BaseModel):
    from_order: int = Field(..., ge=0)
    to_order: int = Field(..., ge=0)
    distance_m: float = Field(..., ge=0)
    duration_s: float = Field(..., ge=0)


class BatchRouteRequest(BaseModel):
    ordered_points: list[BatchPointInput] = Field(default_factory=list)
    legs: list[RouteLegInput] | None = None
    batch_size: int = 15
    include_transition_point: bool = True


class BatchRoutePoint(BaseModel):
    batch_order: int
    global_order: int
    type: RoutePointType
    label: str | None = None
    latitude: float
    longitude: float
    original_index: int
    is_transition_point: bool


class RouteBatch(BaseModel):
    batch_number: int
    points_count: int
    distance_m: float | None = None
    duration_s: float | None = None
    points: list[BatchRoutePoint]


class BatchRouteResponse(BaseModel):
    status: Literal["completed", "failed"]
    batch_size: int
    total_points: int
    batches_count: int
    batches: list[RouteBatch]
