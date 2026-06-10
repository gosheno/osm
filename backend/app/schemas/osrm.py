from typing import Any

from pydantic import BaseModel, Field


class Coordinate(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class OsrmWaypoint(BaseModel):
    latitude: float
    longitude: float
    name: str | None = None
    distance_m: float | None = None


class OsrmRouteRequest(BaseModel):
    points: list[Coordinate] = Field(..., min_length=2, max_length=100)
    overview: bool = True
    steps: bool = False


class OsrmRouteResponse(BaseModel):
    code: str
    distance_m: float
    duration_s: float
    geometry: dict[str, Any] | None = None
    waypoints: list[OsrmWaypoint]


class OsrmTableRequest(BaseModel):
    points: list[Coordinate] = Field(..., min_length=2, max_length=100)


class OsrmTableResponse(BaseModel):
    code: str
    durations: list[list[float | None]]
    distances: list[list[float | None]]
    sources: list[OsrmWaypoint]
    destinations: list[OsrmWaypoint]


class OsrmHealthResponse(BaseModel):
    status: str
    service: str
    code: str
