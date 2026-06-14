from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


GarImportStatus = Literal["pending", "running", "completed", "failed"]
GarNormalizationStatus = Literal[
    "exact_match",
    "partial_match",
    "ambiguous",
    "not_found",
    "manual_review",
]


class GarImportRequest(BaseModel):
    region: str = Field(default="spb_lenobl", min_length=1)
    path: str = Field(..., min_length=1)


class GarImportResponse(BaseModel):
    status: GarImportStatus
    import_id: int


class GarImportStatusResponse(BaseModel):
    import_id: int
    region: str
    source_path: str
    status: GarImportStatus
    address_objects_imported: int = 0
    houses_imported: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    error_message: str | None = None
    report: dict | None = None
    started_at: str | None = None
    finished_at: str | None = None


class GarAddressVariant(BaseModel):
    normalized_full_address: str
    region: str | None = None
    city: str | None = None
    settlement: str | None = None
    street: str | None = None
    house: str | None = None
    building: str | None = None
    structure: str | None = None
    postcode: str | None = None
    gar_object_id: int | None = None
    gar_house_id: int | None = None
    fias_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


class GarNormalizeResult(BaseModel):
    status: GarNormalizationStatus
    normalized_full_address: str | None = None
    region: str | None = None
    city: str | None = None
    settlement: str | None = None
    district: str | None = None
    street: str | None = None
    house: str | None = None
    building: str | None = None
    structure: str | None = None
    postcode: str | None = None
    gar_object_id: int | None = None
    gar_house_id: int | None = None
    fias_id: str | None = None
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    comment: str | None = None
    variants: list[GarAddressVariant] = Field(default_factory=list)
