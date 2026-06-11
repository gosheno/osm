from __future__ import annotations

from typing import Any


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        details: str | None = None,
        status_code: int = 400,
        field: str | None = None,
        failed_addresses: list[dict[str, Any]] | None = None,
        warnings: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details
        self.status_code = status_code
        self.field = field
        self.failed_addresses = failed_addresses or []
        self.warnings = warnings or []

    def to_dict(self) -> dict[str, Any]:
        error: dict[str, Any] = {
            "code": self.code,
            "message": self.message,
        }

        if self.details is not None:
            error["details"] = self.details
        if self.field is not None:
            error["field"] = self.field

        return {
            "status": "failed",
            "error": error,
            "failed_addresses": self.failed_addresses,
            "warnings": self.warnings,
        }


class ValidationAppError(AppError):
    pass


class GeocodingAppError(AppError):
    pass


class OsrmAppError(AppError):
    pass


class OptimizationAppError(AppError):
    pass


class BatchingAppError(AppError):
    pass


class YandexLinkAppError(AppError):
    pass


class DatabaseAppError(AppError):
    pass
