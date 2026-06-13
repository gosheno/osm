from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.routes import router
from app.config import settings
from app.core.errors import OcrServiceError
from app.core.logging import configure_logging


configure_logging()

app = FastAPI(title="Self-hosted OCR service", version=settings.service_version)
app.include_router(router)


@app.exception_handler(OcrServiceError)
async def ocr_error_handler(_: Request, exc: OcrServiceError) -> JSONResponse:
    return JSONResponse(status_code=exc.status_code, content=exc.to_payload())


@app.exception_handler(Exception)
async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content={
            "status": "error",
            "error_code": "PROCESSING_FAILED",
            "message": str(exc),
        },
    )

