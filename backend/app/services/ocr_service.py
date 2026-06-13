from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from app.core.config import settings


class OcrServiceError(Exception):
    pass


@dataclass(frozen=True)
class OcrLine:
    text: str
    confidence: float | None = None


@dataclass(frozen=True)
class OcrResult:
    engine: str
    raw_text: str
    lines: list[OcrLine]


class OcrServiceClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OCR_SERVICE_URL).rstrip("/")
        self.timeout_s = timeout_s or settings.OCR_REQUEST_TIMEOUT_S

    async def recognize_image(self, image_path: Path) -> OcrResult:
        try:
            return await self._recognize_via_service(image_path)
        except Exception as service_error:
            local = self._recognize_locally_if_available(image_path)
            if local is not None:
                return local
            raise OcrServiceError(
                "OCR service is unavailable. Start the self-hosted OCR container "
                f"or install a local OCR fallback. Details: {service_error}"
            ) from service_error

    async def _recognize_via_service(self, image_path: Path) -> OcrResult:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            with image_path.open("rb") as handle:
                response = await client.post(
                    f"{self.base_url}/ocr",
                    files={"file": (image_path.name, handle, "application/octet-stream")},
                )
            response.raise_for_status()

        payload = response.json()
        return result_from_payload(payload)

    def _recognize_locally_if_available(self, image_path: Path) -> OcrResult | None:
        try:
            import pytesseract
            from PIL import Image
        except Exception:
            return None

        with Image.open(image_path) as image:
            raw_text = pytesseract.image_to_string(image, lang="rus+eng")

        lines = [
            OcrLine(text=line.strip(), confidence=None)
            for line in raw_text.splitlines()
            if line.strip()
        ]
        return OcrResult(engine="tesseract-local", raw_text=raw_text, lines=lines)


def result_from_payload(payload: dict[str, Any]) -> OcrResult:
    raw_lines = payload.get("lines") if isinstance(payload.get("lines"), list) else []
    lines: list[OcrLine] = []

    for item in raw_lines:
        if isinstance(item, str):
            text = item.strip()
            confidence = None
        elif isinstance(item, dict):
            text = str(item.get("text") or "").strip()
            confidence = _safe_float(item.get("confidence"))
        else:
            continue
        if text:
            lines.append(OcrLine(text=text, confidence=confidence))

    raw_text = str(payload.get("raw_text") or "\n".join(line.text for line in lines))
    return OcrResult(
        engine=str(payload.get("engine") or settings.OCR_ENGINE),
        raw_text=raw_text,
        lines=lines,
    )


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
