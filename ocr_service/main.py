from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

from fastapi import FastAPI, File, HTTPException, UploadFile


app = FastAPI(title="Self-hosted OCR service", version="0.1.0")

_OCR = None
_OCR_ENGINE: str | None = None
_OCR_ERROR: str | None = None


@app.get("/health")
def health():
    return {
        "status": "ok" if _OCR_ERROR is None else "degraded",
        "service": "ocr",
        "engine": _OCR_ENGINE or "paddleocr",
        "error": _OCR_ERROR,
    }


@app.post("/ocr")
async def recognize(file: UploadFile = File(...)):
    engine, ocr = _get_ocr()
    suffix = Path(file.filename or "image.png").suffix or ".png"

    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as handle:
        image_path = Path(handle.name)
        handle.write(await file.read())

    try:
        if engine == "tesseract":
            lines = _recognize_tesseract(ocr, image_path)
        else:
            try:
                result = ocr.ocr(str(image_path))
                lines = _extract_lines(result)
            except Exception as exc:
                engine = "tesseract"
                ocr = _activate_tesseract_fallback(exc)
                lines = _recognize_tesseract(ocr, image_path)
        return {
            "engine": engine,
            "raw_text": "\n".join(item["text"] for item in lines),
            "lines": lines,
        }
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"OCR recognition failed: {exc}")
    finally:
        image_path.unlink(missing_ok=True)


def _get_ocr():
    global _OCR, _OCR_ENGINE, _OCR_ERROR
    if _OCR is not None:
        return _OCR_ENGINE or "paddleocr", _OCR

    paddle_error: Exception | None = None
    try:
        from paddleocr import PaddleOCR

        attempts = [
            {"use_textline_orientation": True, "lang": "ru"},
            {"use_angle_cls": True, "lang": "ru"},
            {"lang": "ru"},
        ]
        last_error: Exception | None = None
        for kwargs in attempts:
            try:
                _OCR = PaddleOCR(**kwargs)
                _OCR_ENGINE = "paddleocr"
                _OCR_ERROR = None
                return _OCR_ENGINE, _OCR
            except Exception as exc:
                last_error = exc
        if last_error is not None:
            raise last_error
    except Exception as exc:
        paddle_error = exc

    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        _OCR = pytesseract
        _OCR_ENGINE = "tesseract"
        _OCR_ERROR = f"PaddleOCR is unavailable; using Tesseract fallback: {paddle_error}"
        return _OCR_ENGINE, _OCR
    except Exception as exc:
        _OCR_ERROR = f"PaddleOCR is unavailable: {paddle_error}. Tesseract is unavailable: {exc}"
        raise HTTPException(status_code=503, detail=_OCR_ERROR)


def _recognize_tesseract(pytesseract: Any, image_path: Path) -> list[dict[str, Any]]:
    from PIL import Image, ImageEnhance, ImageFilter, ImageOps

    source = Image.open(image_path)
    passes = (
        (None, 6),
        (None, 11),
        ((0.05, 0.22, 0.95, 0.93), 11),
        ((0.35, 0.18, 0.94, 0.94), 11),
        ((0.35, 0.18, 0.94, 0.94), 4),
        ((0.05, 0.38, 0.95, 0.93), 6),
    )

    lines: list[dict[str, Any]] = []
    seen: set[str] = set()
    for crop_box, psm in passes:
        image = _prepare_tesseract_image(source, crop_box, Image, ImageEnhance, ImageFilter, ImageOps)
        for line in _recognize_tesseract_pass(pytesseract, image, psm):
            key = _line_dedupe_key(line["text"])
            if key in seen:
                continue
            seen.add(key)
            lines.append(line)
    return lines


def _prepare_tesseract_image(
    source: Any,
    crop_box: tuple[float, float, float, float] | None,
    Image: Any,
    ImageEnhance: Any,
    ImageFilter: Any,
    ImageOps: Any,
) -> Any:
    image = source
    if crop_box is not None:
        width, height = image.size
        left, top, right, bottom = crop_box
        image = image.crop(
            (
                int(width * left),
                int(height * top),
                int(width * right),
                int(height * bottom),
            )
        )
    image = ImageOps.exif_transpose(image).convert("L")
    max_side = max(image.size)
    if max_side < 2600:
        scale = 2600 / max_side
        image = image.resize(
            (int(image.width * scale), int(image.height * scale)),
            Image.Resampling.LANCZOS,
        )
    image = ImageEnhance.Contrast(image).enhance(1.8)
    image = image.filter(ImageFilter.SHARPEN)
    return image


def _recognize_tesseract_pass(pytesseract: Any, image: Any, psm: int) -> list[dict[str, Any]]:
    data = pytesseract.image_to_data(
        image,
        lang="rus+eng",
        config=f"--oem 1 --psm {psm}",
        output_type=pytesseract.Output.DICT,
    )

    grouped: dict[tuple[int, int, int], dict[str, Any]] = {}
    count = len(data.get("text", []))
    for index in range(count):
        text = str(data["text"][index] or "").strip()
        if not text:
            continue
        text = _repair_mojibake_text(text)
        key = (
            int(data.get("block_num", [0])[index] or 0),
            int(data.get("par_num", [0])[index] or 0),
            int(data.get("line_num", [0])[index] or 0),
        )
        confidence = _safe_float(data.get("conf", [None])[index])
        bucket = grouped.setdefault(key, {"words": [], "confidences": []})
        bucket["words"].append(text)
        if confidence is not None and confidence >= 0:
            bucket["confidences"].append(confidence / 100)

    lines: list[dict[str, Any]] = []
    for key in sorted(grouped):
        bucket = grouped[key]
        text = " ".join(bucket["words"]).strip()
        text = _repair_mojibake_text(text)
        if not text:
            continue
        confidences = bucket["confidences"]
        confidence = sum(confidences) / len(confidences) if confidences else None
        lines.append({"text": text, "confidence": confidence})
    return lines


def _line_dedupe_key(text: str) -> str:
    return " ".join(text.lower().split())


def _repair_mojibake_text(text: str) -> str:
    markers = ("Р", "С", "Ð", "Ñ", "вЂ")
    if not any(marker in text for marker in markers):
        return text
    repaired = None
    for errors in ("strict", "ignore"):
        try:
            repaired = text.encode("cp1251", errors=errors).decode("utf-8", errors=errors)
            break
        except UnicodeError:
            continue
    if repaired is None:
        return text
    if _mojibake_score(repaired) < _mojibake_score(text) and _has_cyrillic(repaired):
        return repaired
    return text


def _mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in ("Р", "С", "Ð", "Ñ", "вЂ"))


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04ff" for char in text)


def _activate_tesseract_fallback(paddle_error: Exception) -> Any:
    global _OCR, _OCR_ENGINE, _OCR_ERROR
    try:
        import pytesseract

        pytesseract.get_tesseract_version()
        _OCR = pytesseract
        _OCR_ENGINE = "tesseract"
        _OCR_ERROR = f"PaddleOCR failed; using Tesseract fallback: {paddle_error}"
        return _OCR
    except Exception as exc:
        _OCR_ERROR = f"PaddleOCR failed: {paddle_error}. Tesseract is unavailable: {exc}"
        raise HTTPException(status_code=503, detail=_OCR_ERROR)


def _extract_lines(result: Any) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for item in _walk_ocr_items(result):
        parsed = _parse_line(item)
        if parsed is not None:
            lines.append(parsed)
    return lines


def _walk_ocr_items(value: Any):
    if isinstance(value, dict):
        texts = value.get("rec_texts")
        if isinstance(texts, list):
            scores = value.get("rec_scores") or []
            for index, text in enumerate(texts):
                yield {
                    "text": text,
                    "confidence": scores[index] if index < len(scores) else None,
                }
            return
        yield value
        return

    if not isinstance(value, list):
        return
    if _parse_line(value) is not None:
        yield value
        return
    for item in value:
        if isinstance(item, (dict, list)):
            yield from _walk_ocr_items(item)


def _parse_line(item: Any) -> dict[str, Any] | None:
    if (
        isinstance(item, list)
        and len(item) >= 2
        and isinstance(item[1], (list, tuple))
        and len(item[1]) >= 1
    ):
        text = str(item[1][0] or "").strip()
        if not text:
            return None
        confidence = None
        if len(item[1]) >= 2:
            try:
                confidence = float(item[1][1])
            except (TypeError, ValueError):
                confidence = None
        return {"text": text, "confidence": confidence}

    if isinstance(item, dict):
        text = str(item.get("text") or item.get("rec_text") or "").strip()
        if text:
            return {
                "text": text,
                "confidence": _safe_float(item.get("confidence") or item.get("score")),
            }

    return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None
