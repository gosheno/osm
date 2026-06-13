from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.schemas.route import OptimizeRouteByAddressesResponse


RouteImportStatus = Literal[
    "uploaded",
    "processing",
    "completed",
    "failed",
    "confirmed",
]
RouteImportItemStatus = Literal[
    "recognized",
    "needs_review",
    "confirmed",
    "rejected",
    "duplicate",
]


class RouteImportImageRead(BaseModel):
    id: int
    import_id: int
    file_path: str
    original_filename: str
    image_order: int
    preprocessed_file_path: str | None = None
    ocr_status: str
    error_message: str | None = None


class RouteImportItemRead(BaseModel):
    id: int
    import_id: int
    source_image_id: int | None = None
    row_number: int
    raw_ocr_text: str
    store_name: str | None = None
    address: str | None = None
    normalized_address: str | None = None
    user_corrected_store_name: str | None = None
    user_corrected_address: str | None = None
    confidence_score: float | None = None
    geocoding_status: str | None = None
    address_id: int | None = None
    status: str
    error_message: str | None = None
    possible_duplicate_of_id: int | None = None


class RouteImportRead(BaseModel):
    import_id: int
    status: str
    source_type: str
    ocr_engine: str | None = None
    raw_text: str | None = None
    error_message: str | None = None
    images: list[RouteImportImageRead] = Field(default_factory=list)
    items: list[RouteImportItemRead] = Field(default_factory=list)


class RouteImportCreateResponse(BaseModel):
    import_id: int
    status: str


class RouteImportItemPatchRequest(BaseModel):
    store_name: str | None = None
    address: str | None = None
    status: RouteImportItemStatus | None = None


class RouteImportConfirmRequest(BaseModel):
    start_address: str = Field(..., min_length=1)
    end_address: str = Field(..., min_length=1)
    batch_size: int = Field(default=15, ge=1, le=20)
    include_item_ids: list[int] = Field(default_factory=list)
    exclude_problematic: bool = False
    default_city: str | None = "Санкт-Петербург"
    city_slug: str = "saint-petersburg"
    optimization_metric: str = "duration"


class RouteImportConfirmResponse(BaseModel):
    route_job_id: int | None
    status: str
    included_item_ids: list[int] = Field(default_factory=list)
    excluded_item_ids: list[int] = Field(default_factory=list)
    route: OptimizeRouteByAddressesResponse | None = None
