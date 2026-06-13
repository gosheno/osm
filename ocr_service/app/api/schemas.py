from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


EngineName = Literal["auto", "paddle", "tesseract", "native_paddle"]
CellMode = Literal["raw", "gray", "binary", "auto"]
LineMode = Literal["soft", "aggressive"]


class WarningItem(BaseModel):
    code: str
    message: str


class ImageInfo(BaseModel):
    width: int
    height: int
    format: str | None = None


class OcrLine(BaseModel):
    text: str
    confidence: float | None = None


class OcrCell(BaseModel):
    column_index: int
    text: str
    confidence: float | None = None


class OcrTableRow(BaseModel):
    row_index: int
    cells: list[OcrCell] = Field(default_factory=list)
    row_confidence: float | None = None
    raw_text: str = ""


class OcrTable(BaseModel):
    rows_count: int
    columns_count: int
    rows: list[OcrTableRow] = Field(default_factory=list)


class RoutePoint(BaseModel):
    source_row_index: int
    original_order: int | None = None
    name: str | None = None
    address: str
    raw_row_text: str = ""
    confidence: float | None = None
    warnings: list[WarningItem] = Field(default_factory=list)


class DebugArtifact(BaseModel):
    name: str
    type: str = "image/png"
    base64: str | None = None
    url: str | None = None


class DebugInfo(BaseModel):
    enabled: bool = False
    artifacts: list[DebugArtifact] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    service: str = "ocr"
    version: str
    engines: dict[str, dict[str, object]]
    error: str | None = None


class PlainTextResponse(BaseModel):
    status: str = "ok"
    engine: str
    mode: str = "plain_text"
    raw_text: str
    lines: list[OcrLine] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    processing_time_ms: int | None = None
    image_info: ImageInfo | None = None


class RouteTableResponse(BaseModel):
    status: str = "ok"
    engine: str
    mode: str = "route_table"
    raw_text: str
    table: OcrTable
    route_points: list[RoutePoint] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)
    debug: DebugInfo = Field(default_factory=DebugInfo)
    processing_time_ms: int | None = None
    image_info: ImageInfo | None = None


class DebugTableResponse(BaseModel):
    status: str = "ok"
    table_detected: bool
    rows_count: int
    columns_count: int
    cells_count: int
    debug_artifacts: list[DebugArtifact] = Field(default_factory=list)
    warnings: list[WarningItem] = Field(default_factory=list)

