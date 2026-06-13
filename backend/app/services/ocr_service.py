from __future__ import annotations

from dataclasses import dataclass, field
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
class OcrRoutePoint:
    source_row_index: int
    address: str
    original_order: int | None = None
    name: str | None = None
    raw_row_text: str = ""
    confidence: float | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class OcrResult:
    engine: str
    raw_text: str
    lines: list[OcrLine]
    route_points: list[OcrRoutePoint] = field(default_factory=list)
    table: dict[str, Any] | None = None
    warnings: list[dict[str, Any]] = field(default_factory=list)


class OcrServiceClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_s: float | None = None,
    ) -> None:
        self.base_url = (base_url or settings.OCR_SERVICE_URL).rstrip("/")
        self.timeout_s = timeout_s or settings.OCR_REQUEST_TIMEOUT_S

    async def recognize_image(
        self,
        image_path: Path,
        *,
        debug: bool = False,
        line_mode: str = "aggressive",
        cell_mode: str = "auto",
    ) -> OcrResult:
        try:
            return await self._recognize_via_service(
                image_path,
                debug=debug,
                line_mode=line_mode,
                cell_mode=cell_mode,
            )
        except httpx.HTTPStatusError as service_error:
            response = service_error.response
            if 400 <= response.status_code < 500:
                raise OcrServiceError(_service_error_message(response)) from service_error
            local = self._recognize_locally_if_available(image_path)
            if local is not None:
                return local
            raise OcrServiceError(
                "OCR service failed and no local OCR fallback is available. "
                f"Details: {_service_error_message(response)}"
            ) from service_error
        except Exception as service_error:
            local = self._recognize_locally_if_available(image_path)
            if local is not None:
                return local
            raise OcrServiceError(
                "OCR service is unavailable. Start the self-hosted OCR container "
                f"or install a local OCR fallback. Details: {service_error}"
            ) from service_error

    async def _recognize_via_service(
        self,
        image_path: Path,
        *,
        debug: bool,
        line_mode: str,
        cell_mode: str,
    ) -> OcrResult:
        async with httpx.AsyncClient(timeout=self.timeout_s) as client:
            with image_path.open("rb") as handle:
                response = await client.post(
                    f"{self.base_url}/api/ocr/route-table",
                    files={"file": (image_path.name, handle, "application/octet-stream")},
                    data={
                        "engine": settings.OCR_ENGINE,
                        "lang": "ru",
                        "cell_mode": cell_mode,
                        "line_mode": line_mode,
                        "debug": str(debug).lower(),
                        "extract_addresses": "true",
                    },
                )
            if response.status_code == 404:
                return await self._recognize_legacy(client, image_path)
            response.raise_for_status()

        payload = response.json()
        return result_from_payload(payload)

    async def _recognize_legacy(self, client: httpx.AsyncClient, image_path: Path) -> OcrResult:
        with image_path.open("rb") as handle:
            response = await client.post(
                f"{self.base_url}/ocr",
                files={"file": (image_path.name, handle, "application/octet-stream")},
            )
        response.raise_for_status()
        return result_from_payload(response.json())

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

    route_points = _route_points_from_payload(payload)
    if route_points and not lines:
        lines = [
            OcrLine(
                text=point.raw_row_text or point.address,
                confidence=point.confidence,
            )
            for point in route_points
        ]

    if not lines:
        lines.extend(_lines_from_table_payload(payload.get("table")))

    raw_text = str(payload.get("raw_text") or "\n".join(line.text for line in lines))
    return OcrResult(
        engine=str(payload.get("engine") or settings.OCR_ENGINE),
        raw_text=raw_text,
        lines=lines,
        route_points=route_points,
        table=payload.get("table") if isinstance(payload.get("table"), dict) else None,
        warnings=payload.get("warnings") if isinstance(payload.get("warnings"), list) else [],
    )


def _route_points_from_payload(payload: dict[str, Any]) -> list[OcrRoutePoint]:
    raw_points = payload.get("route_points") if isinstance(payload.get("route_points"), list) else []
    points: list[OcrRoutePoint] = []
    for item in raw_points:
        if not isinstance(item, dict):
            continue
        address = str(item.get("address") or "").strip()
        if not address:
            continue
        points.append(
            OcrRoutePoint(
                source_row_index=int(item.get("source_row_index") or 0),
                original_order=_safe_int(item.get("original_order")),
                name=str(item.get("name")).strip() if item.get("name") else None,
                address=address,
                raw_row_text=str(item.get("raw_row_text") or item.get("raw_text") or address),
                confidence=_safe_float(item.get("confidence")),
                warnings=item.get("warnings") if isinstance(item.get("warnings"), list) else [],
            )
        )
    return points


def _lines_from_table_payload(table: Any) -> list[OcrLine]:
    if not isinstance(table, dict):
        return []
    rows = table.get("rows") if isinstance(table.get("rows"), list) else []
    lines: list[OcrLine] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        text = str(row.get("raw_text") or "").strip()
        if not text:
            cells = row.get("cells") if isinstance(row.get("cells"), list) else []
            text = " ".join(
                str(cell.get("text") or "").strip()
                for cell in cells
                if isinstance(cell, dict) and str(cell.get("text") or "").strip()
            )
        if text:
            lines.append(OcrLine(text=text, confidence=_safe_float(row.get("row_confidence"))))
    return lines


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _service_error_message(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except Exception:
        return response.text
    if isinstance(payload, dict):
        if payload.get("message"):
            code = payload.get("error_code")
            return f"{code}: {payload['message']}" if code else str(payload["message"])
        if payload.get("detail"):
            return str(payload["detail"])
    return str(payload)
