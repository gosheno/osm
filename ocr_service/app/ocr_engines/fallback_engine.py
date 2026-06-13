from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from app.core.errors import EngineUnavailableError
from app.ocr_engines.base import OcrEngine
from app.ocr_engines.paddle_engine import PaddleEngine
from app.ocr_engines.tesseract_engine import TesseractEngine


@dataclass
class EngineSelection:
    engine: OcrEngine
    warnings: list[dict[str, str]] = field(default_factory=list)


class OcrEngineManager:
    def __init__(self) -> None:
        self.paddle = PaddleEngine()
        self.tesseract = TesseractEngine()

    def health(self) -> dict[str, dict[str, object]]:
        return {
            "paddle": {
                "available": PaddleEngine.is_available(),
                "loaded": self.paddle.loaded,
            },
            "tesseract": {
                "available": TesseractEngine.is_available(),
                "loaded": self.tesseract.loaded,
                "version": self.tesseract.version() if TesseractEngine.is_available() else None,
            },
        }

    def select(self, engine_name: str) -> EngineSelection:
        normalized = _normalize_engine_name(engine_name)
        if normalized == "paddle":
            if not PaddleEngine.is_available():
                raise EngineUnavailableError("PaddleOCR is unavailable")
            return EngineSelection(self.paddle)
        if normalized == "native_paddle":
            if not PaddleEngine.is_available():
                raise EngineUnavailableError("PaddleOCR is unavailable")
            return EngineSelection(
                self.paddle,
                warnings=[
                    {
                        "code": "NATIVE_PADDLE_EXPERIMENTAL",
                        "message": "native_paddle is experimental; OpenCV table structure is still used for this request",
                    }
                ],
            )
        if normalized == "tesseract":
            if not TesseractEngine.is_available():
                raise EngineUnavailableError("Tesseract is unavailable")
            return EngineSelection(self.tesseract)

        if PaddleEngine.is_available():
            return EngineSelection(self.paddle)
        if TesseractEngine.is_available():
            return EngineSelection(
                self.tesseract,
                warnings=[
                    {
                        "code": "OCR_ENGINE_FALLBACK",
                        "message": "PaddleOCR unavailable, Tesseract fallback was used",
                    }
                ],
            )
        raise EngineUnavailableError("No OCR engine is available")

    def fallback_to_tesseract(self, original_error: Exception) -> EngineSelection:
        if not TesseractEngine.is_available():
            raise EngineUnavailableError(f"PaddleOCR failed and Tesseract is unavailable: {original_error}")
        return EngineSelection(
            self.tesseract,
            warnings=[
                {
                    "code": "OCR_ENGINE_FALLBACK",
                    "message": "PaddleOCR failed, Tesseract fallback was used",
                }
            ],
        )


def _normalize_engine_name(engine_name: str) -> str:
    if engine_name == "paddleocr":
        return "paddle"
    return (engine_name or "auto").lower()


engine_manager = OcrEngineManager()

