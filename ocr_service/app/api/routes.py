from __future__ import annotations

from fastapi import APIRouter, File, Form, UploadFile

from app.api.schemas import CellMode, EngineName, LineMode
from app.config import settings
from app.core.pipeline import (
    PlainTextOptions,
    RouteTableOptions,
    process_debug_table,
    process_plain_text,
    process_route_table,
)
from app.ocr_engines.fallback_engine import engine_manager


router = APIRouter()


@router.get("/health")
def health() -> dict[str, object]:
    engines = engine_manager.health()
    paddle_available = bool(engines["paddle"]["available"])
    tesseract_available = bool(engines["tesseract"]["available"])
    if paddle_available:
        status = "ok"
        error = None
    elif tesseract_available:
        status = "degraded"
        error = "PaddleOCR unavailable, Tesseract fallback active"
    else:
        status = "degraded"
        error = "No OCR engine is available"
    return {
        "status": status,
        "service": "ocr",
        "version": settings.service_version,
        "engines": engines,
        "error": error,
    }


@router.post("/api/ocr/text")
async def plain_text(
    file: UploadFile = File(...),
    engine: EngineName = Form("auto"),
    lang: str = Form(settings.default_lang),
) -> dict[str, object]:
    return process_plain_text(
        file.filename,
        await file.read(),
        PlainTextOptions(engine=engine, lang=lang),
    )


@router.post("/api/ocr/route-table")
async def route_table(
    file: UploadFile = File(...),
    engine: EngineName = Form("auto"),
    lang: str = Form(settings.default_lang),
    cell_mode: CellMode = Form("auto"),
    line_mode: LineMode = Form("aggressive"),
    debug: bool = Form(False),
    extract_addresses: bool = Form(True),
) -> dict[str, object]:
    return process_route_table(
        file.filename,
        await file.read(),
        RouteTableOptions(
            engine=engine,
            lang=lang,
            cell_mode=cell_mode,
            line_mode=line_mode,
            debug=debug,
            extract_addresses=extract_addresses,
        ),
    )


@router.post("/api/ocr/debug-table")
async def debug_table(
    file: UploadFile = File(...),
    line_mode: LineMode = Form("aggressive"),
) -> dict[str, object]:
    return process_debug_table(file.filename, await file.read(), line_mode=line_mode)


@router.post("/ocr")
async def legacy_ocr(
    file: UploadFile = File(...),
    engine: EngineName = Form("auto"),
    lang: str = Form(settings.default_lang),
) -> dict[str, object]:
    return await plain_text(file=file, engine=engine, lang=lang)

