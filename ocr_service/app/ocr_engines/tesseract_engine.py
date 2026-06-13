from __future__ import annotations

import importlib.util
import shutil
import threading
from typing import Any

import cv2

from app.ocr_engines.base import OcrToken, cleanup_text


class TesseractEngine:
    name = "tesseract"

    def __init__(self, *, min_conf: float = 20.0) -> None:
        self.min_conf = min_conf
        self._module: Any | None = None
        self._lock = threading.Lock()

    @staticmethod
    def is_available() -> bool:
        return importlib.util.find_spec("pytesseract") is not None and shutil.which("tesseract") is not None

    @property
    def loaded(self) -> bool:
        return self._module is not None

    def version(self) -> str | None:
        try:
            module = self._get_module()
            return str(module.get_tesseract_version())
        except Exception:
            return None

    def recognize_lines(self, image: Any, *, lang: str) -> list[OcrToken]:
        module = self._get_module()
        prepared = _to_gray(image)
        data = module.image_to_data(
            prepared,
            lang=_normalize_lang(lang),
            config="--oem 3 --psm 6 -c preserve_interword_spaces=1 -c user_defined_dpi=300",
            output_type=module.Output.DICT,
        )
        grouped: dict[tuple[int, int, int], dict[str, list[Any]]] = {}
        for index, text in enumerate(data.get("text", [])):
            text = cleanup_text(text)
            if not text:
                continue
            key = (
                int(data.get("block_num", [0])[index] or 0),
                int(data.get("par_num", [0])[index] or 0),
                int(data.get("line_num", [0])[index] or 0),
            )
            bucket = grouped.setdefault(key, {"words": [], "conf": []})
            bucket["words"].append(text)
            conf = _safe_float(data.get("conf", [None])[index])
            if conf is not None and conf >= 0:
                bucket["conf"].append(conf / 100)

        lines: list[OcrToken] = []
        for key in sorted(grouped):
            bucket = grouped[key]
            text = cleanup_text(" ".join(bucket["words"]))
            if text:
                lines.append(OcrToken(text, _average(bucket["conf"])))
        return lines

    def recognize_cell(self, image: Any, *, lang: str) -> OcrToken:
        module = self._get_module()
        height, width = image.shape[:2]
        psm = 7 if width < 220 or height < 55 else 6
        config = (
            f"--oem 3 --psm {psm} "
            "-c preserve_interword_spaces=1 "
            "-c user_defined_dpi=300"
        )
        data = module.image_to_data(
            image,
            lang=_normalize_lang(lang),
            config=config,
            output_type=module.Output.DICT,
        )
        tokens: list[str] = []
        confidences: list[float] = []
        for text, conf in zip(data.get("text", []), data.get("conf", [])):
            text = cleanup_text(text)
            if not text:
                continue
            conf_value = _safe_float(conf)
            if conf_value is None:
                continue
            if conf_value >= self.min_conf or conf_value < 0:
                tokens.append(text)
                if conf_value >= 0:
                    confidences.append(conf_value / 100)
        if tokens:
            return OcrToken(cleanup_text(" ".join(tokens)), _average(confidences))

        fallback = cleanup_text(module.image_to_string(image, lang=_normalize_lang(lang), config=config))
        return OcrToken(fallback, None)

    def _get_module(self) -> Any:
        with self._lock:
            if self._module is None:
                import pytesseract

                pytesseract.get_tesseract_version()
                self._module = pytesseract
            return self._module


def _to_gray(image: Any) -> Any:
    if len(image.shape) == 2:
        return image
    return cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)


def _normalize_lang(lang: str) -> str:
    if lang.lower() in {"ru", "rus", "russian", "cyrillic"}:
        return "rus+eng"
    return lang


def _safe_float(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None

