from __future__ import annotations

import logging
import traceback

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    logger.error(
        "AppError: %s %s %s %s",
        exc.code,
        exc.message,
        exc.details,
        request.url.path,
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=exc.to_dict(),
    )


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "ValidationError: %s %s",
        request.url.path,
        exc.errors(),
    )

    return JSONResponse(
        status_code=422,
        content={
            "status": "failed",
            "error": {
                "code": "VALIDATION_ERROR",
                "message": "Проверьте корректность заполнения формы.",
                "details": exc.errors(),
            },
            "failed_addresses": [],
            "warnings": [],
        },
    )


def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception(
        "Unexpected error on %s: %s",
        request.url.path,
        exc,
    )

    return JSONResponse(
        status_code=500,
        content={
            "status": "failed",
            "error": {
                "code": "INTERNAL_SERVER_ERROR",
                "message": "Произошла внутренняя ошибка сервера.",
                "details": "Unexpected server error",
            },
            "failed_addresses": [],
            "warnings": [],
        },
    )


def http_exception_handler(request: Request, exc: HTTPException) -> JSONResponse:
    logger.warning(
        "HTTPException: %s %s %s",
        exc.status_code,
        exc.detail,
        request.url.path,
    )

    detail = exc.detail
    if isinstance(detail, dict) and detail.get("error"):
        return JSONResponse(
            status_code=exc.status_code,
            content=detail,
        )

    error_response = {
        "status": "failed",
        "error": {
            "code": "INTERNAL_SERVER_ERROR" if exc.status_code >= 500 else "VALIDATION_ERROR",
            "message": "Произошла ошибка сервера." if exc.status_code >= 500 else "Проверьте корректность заполнения формы.",
            "details": str(detail),
        },
        "failed_addresses": [],
        "warnings": [],
    }

    return JSONResponse(status_code=exc.status_code, content=error_response)


def register_error_handlers(app) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(Exception, unexpected_error_handler)
