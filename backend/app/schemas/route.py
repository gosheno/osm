from typing import Any, Literal

from pydantic import BaseModel, Field

from app.schemas.geocoding import GeocodingContextInput
from app.schemas.optimization import OptimizationMetric, RoutePointType


RouteBuildStatus = Literal["completed", "failed", "completed_with_warnings"]
RouteAddressRole = Literal["start", "waypoint", "end"]


class SelectedRouteAddress(BaseModel):
    address_id: int | None = None
    display_name: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    confidence_score: float | None = None
    geocoding_status: str | None = "found"


class OptimizeRouteByAddressesRequest(BaseModel):
    start_address: str = Field(..., min_length=1)
    end_address: str = Field(..., min_length=1)
    addresses: list[str] = Field(default_factory=list, max_length=100)
    batch_size: int = Field(default=15, ge=1, le=20)
    optimization_metric: OptimizationMetric = "duration"
    city_slug: str = "saint-petersburg"
    default_city: str | None = "санкт-петербург"
    force_refresh: bool = False
    geocoding_context: GeocodingContextInput | None = None
    geocoding_area: str | None = None
    start_selected: SelectedRouteAddress | None = None
    end_selected: SelectedRouteAddress | None = None
    waypoints_selected: list[SelectedRouteAddress | None] = Field(default_factory=list, max_length=100)


class RouteAddressResult(BaseModel):
    id: int | None = None
    role: RouteAddressRole
    input_index: int
    original_index: int
    input_address: str
    original_address: str | None = None
    address_for_geocoding: str | None = None
    normalized_address: str | None = None
    place_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geocoding_status: str | None = None
    geocoding_provider: str | None = None
    confidence_score: float | None = None
    geocoding_score: float | None = None
    geocoding_query: str | None = None
    geocoding_context_label: str | None = None
    distance_to_context_m: float | None = None
    source: str | None = None
    from_cache: bool = False
    error: str | None = None


class FailedAddressResult(BaseModel):
    type: RouteAddressRole
    input_index: int
    original_index: int
    input_address: str
    address_for_geocoding: str | None = None
    normalized_address: str | None = None
    place_name: str | None = None
    geocoding_status: str | None = None
    geocoding_provider: str | None = None
    geocoding_score: float | None = None
    geocoding_query: str | None = None
    geocoding_context_label: str | None = None
    source: str | None = None
    error: str
    reason: str | None = None
    code: str | None = None


class RouteLegResult(BaseModel):
    from_order: int
    to_order: int
    distance_m: float
    duration_s: float


class OptimizedRoutePointResult(BaseModel):
    order: int
    type: RoutePointType
    label: str | None = None
    latitude: float
    longitude: float
    original_index: int
    district: str | None = None
    address: RouteAddressResult | None = None


class RouteBatchPointResult(BaseModel):
    batch_order: int
    global_order: int
    type: RoutePointType
    label: str | None = None
    latitude: float
    longitude: float
    original_index: int
    is_transition_point: bool
    district: str | None = None


class RouteBatchResult(BaseModel):
    batch_number: int
    points_count: int
    district: str | None = None
    districts: list[str] = Field(default_factory=list)
    distance_m: float | None = None
    duration_s: float | None = None
    url_length: int | None = None
    has_warning: bool = False
    warnings: list[str] = Field(default_factory=list)
    yandex_maps_url: str | None = None
    points: list[RouteBatchPointResult]


class OptimizeRouteByAddressesResponse(BaseModel):
    status: RouteBuildStatus
    route_job_id: int | None = None
    total_input_addresses: int
    total_addresses: int
    total_points: int
    total_distance_m: float | None = None
    total_duration_s: float | None = None
    optimization_metric: OptimizationMetric
    batch_size: int
    city_slug: str
    geocoded_addresses: list[RouteAddressResult] = Field(default_factory=list)
    failed_addresses: list[FailedAddressResult] = Field(default_factory=list)
    ordered_points: list[OptimizedRoutePointResult] = Field(default_factory=list)
    route_geometry: dict[str, Any] | None = None
    legs: list[RouteLegResult] = Field(default_factory=list)
    batches: list[RouteBatchResult] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
