from typing import Literal

from pydantic import BaseModel, Field


OptimizationMetric = Literal["duration", "distance"]
RoutePointType = Literal["start", "waypoint", "end"]


class CoordinateInput(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    label: str | None = None


class OptimizationPoint(CoordinateInput):
    type: RoutePointType
    original_index: int


class OptimizeRouteRequest(BaseModel):
    start: CoordinateInput
    end: CoordinateInput
    points: list[CoordinateInput] = Field(default_factory=list)
    optimization_metric: OptimizationMetric = "duration"


class OrderedRoutePoint(BaseModel):
    order: int
    type: RoutePointType
    label: str | None = None
    latitude: float
    longitude: float
    original_index: int


class OptimizedRouteLeg(BaseModel):
    from_order: int
    to_order: int
    distance_m: float
    duration_s: float


class OptimizeRouteResponse(BaseModel):
    status: Literal["completed", "failed"]
    optimization_metric: OptimizationMetric
    points_count: int
    total_distance_m: float
    total_duration_s: float
    initial_duration_s: float
    optimized_duration_s: float
    improvement_duration_s: float
    improvement_percent: float
    ordered_points: list[OrderedRoutePoint]
    legs: list[OptimizedRouteLeg]
