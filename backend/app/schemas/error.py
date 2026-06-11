from typing import Literal

from pydantic import BaseModel, Field


WarningType = Literal["string", "object"]


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: str | None = None
    field: str | None = None


class FailedAddressDetail(BaseModel):
    type: Literal["start", "waypoint", "end"]
    original_address: str
    normalized_address: str | None = None
    reason: str
    code: str
    geocoding_status: str | None = None


class WarningDetail(BaseModel):
    code: str
    message: str
    details: str | None = None
    related_item: str | None = None


class ErrorResponse(BaseModel):
    status: Literal["failed"]
    error: ErrorDetail
    failed_addresses: list[FailedAddressDetail] = Field(default_factory=list)
    warnings: list[WarningDetail] = Field(default_factory=list)
