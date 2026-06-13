from __future__ import annotations

import importlib.util
import threading
from typing import Any

from app.ocr_engines.base import OcrToken, cleanup_text, collect_ocr_pairs


class PaddleEngine:
    name = "paddle"

    def __init__(self, *, min_score: float = 0.35) -> None:
        self.min_score = min_score
        self._recognition: Any | None = None
        self._pipeline: Any | None = None
        self._lock = threading.Lock()

    @staticmethod
    def is_available() -> bool:
        return (
            importlib.util.find_spec("paddleocr") is not None
            and importlib.util.find_spec("paddle") is not None
        )

    @property
    def loaded(self) -> bool:
        return self._recognition is not None or self._pipeline is not None

    def recognize_cell(self, image: Any, *, lang: str) -> OcrToken:
        engine = self._get_recognition_engine(lang)
        errors: list[str] = []
        for kwargs in ({"input": image}, {}):
            try:
                result = engine.predict(**kwargs)
                return self._tokens_to_cell(result)
            except TypeError as exc:
                errors.append(f"predict kwargs={kwargs}: {exc}")
            except Exception as exc:
                errors.append(f"predict kwargs={kwargs}: {exc}")
        raise RuntimeError("PaddleOCR cell recognition failed: " + " | ".join(errors[-3:]))

    def recognize_lines(self, image: Any, *, lang: str) -> list[OcrToken]:
        engine = self._get_pipeline_engine(lang)
        errors: list[str] = []
        if hasattr(engine, "ocr"):
            for kwargs in ({"cls": True}, {}):
                try:
                    return self._tokens_from_result(engine.ocr(image, **kwargs))
                except TypeError as exc:
                    errors.append(f"ocr kwargs={kwargs}: {exc}")
                except Exception as exc:
                    errors.append(f"ocr kwargs={kwargs}: {exc}")
        if hasattr(engine, "predict"):
            for kwargs in ({"input": image}, {}):
                try:
                    return self._tokens_from_result(engine.predict(**kwargs))
                except TypeError as exc:
                    errors.append(f"predict kwargs={kwargs}: {exc}")
                except Exception as exc:
                    errors.append(f"predict kwargs={kwargs}: {exc}")
        raise RuntimeError("PaddleOCR recognition failed: " + " | ".join(errors[-4:]))

    def _get_recognition_engine(self, lang: str) -> Any:
        with self._lock:
            if self._recognition is not None:
                return self._recognition
            from paddleocr import TextRecognition

            model_name = "eslav_PP-OCRv5_mobile_rec" if lang.lower() in {"ru", "rus", "russian"} else None
            kwargs = {"model_name": model_name} if model_name else {}
            self._recognition = TextRecognition(**kwargs)
            return self._recognition

    def _get_pipeline_engine(self, lang: str) -> Any:
        with self._lock:
            if self._pipeline is not None:
                return self._pipeline
            from paddleocr import PaddleOCR

            attempts: list[dict[str, Any]] = [
                {
                    "lang": lang,
                    "use_doc_orientation_classify": False,
                    "use_doc_unwarping": False,
                    "use_textline_orientation": False,
                },
                {"use_textline_orientation": True, "lang": lang},
                {"use_angle_cls": True, "lang": lang},
                {"lang": lang},
            ]
            errors: list[str] = []
            for kwargs in attempts:
                try:
                    self._pipeline = PaddleOCR(**kwargs)
                    return self._pipeline
                except Exception as exc:
                    errors.append(f"{kwargs}: {exc}")
            raise RuntimeError("Could not initialize PaddleOCR: " + " | ".join(errors[-3:]))

    def _tokens_to_cell(self, result: Any) -> OcrToken:
        tokens = self._tokens_from_result(result)
        texts: list[str] = []
        scores: list[float] = []
        for token in tokens:
            if token.confidence is None or token.confidence >= self.min_score:
                texts.append(token.text)
                if token.confidence is not None:
                    scores.append(token.confidence)
        return OcrToken(cleanup_text(" ".join(texts)), _average(scores))

    def _tokens_from_result(self, result: Any) -> list[OcrToken]:
        return collect_ocr_pairs(result)


def _average(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None
