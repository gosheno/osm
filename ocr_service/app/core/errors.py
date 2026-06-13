from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class OcrServiceError(Exception):
    error_code: str
    message: str
    status_code: int = 400
    hints: list[str] = field(default_factory=list)
    details: Any | None = None

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": "error",
            "error_code": self.error_code,
            "message": self.message,
        }
        if self.hints:
            payload["hints"] = self.hints
        if self.details is not None:
            payload["details"] = self.details
        return payload


class InvalidImageError(OcrServiceError):
    def __init__(self, message: str = "Uploaded file is not a supported image") -> None:
        super().__init__("INVALID_IMAGE", message, status_code=400)


class FileTooLargeError(OcrServiceError):
    def __init__(self, max_size_mb: int) -> None:
        super().__init__(
            "FILE_TOO_LARGE",
            f"Maximum allowed file size is {max_size_mb} MB",
            status_code=413,
        )


class EngineUnavailableError(OcrServiceError):
    def __init__(self, message: str = "OCR engine is unavailable") -> None:
        super().__init__("OCR_ENGINE_UNAVAILABLE", message, status_code=503)


class TableNotFoundError(OcrServiceError):
    def __init__(self) -> None:
        super().__init__(
            "TABLE_NOT_FOUND",
            "No table grid was detected in the uploaded image",
            status_code=422,
            hints=[
                "Try a clearer screenshot",
                "Try debug mode",
                "Try line_mode=soft",
            ],
        )


class NoCellsFoundError(OcrServiceError):
    def __init__(self) -> None:
        super().__init__(
            "NO_CELLS_FOUND",
            "No table cells were detected in the uploaded image",
            status_code=422,
            hints=[
                "Try a clearer screenshot",
                "Try debug mode",
                "Try line_mode=soft",
            ],
        )

