from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class OcrToken:
    text: str
    confidence: float | None = None


class OcrEngine(Protocol):
    name: str

    def recognize_lines(self, image: Any, *, lang: str) -> list[OcrToken]:
        ...

    def recognize_cell(self, image: Any, *, lang: str) -> OcrToken:
        ...


def cleanup_text(text: str) -> str:
    text = str(text or "").replace("\n", " ").replace("\r", " ")
    text = text.replace("|", "I")
    text = repair_mojibake_text(text)
    return " ".join(text.split()).strip()


def repair_mojibake_text(text: str) -> str:
    markers = ("Р ", "РЎ", "Гђ", "Г‘", "РІР‚", "Рџ", "РЅ")
    if not any(marker in text for marker in markers):
        return text
    for errors in ("strict", "ignore"):
        try:
            repaired = text.encode("cp1251", errors=errors).decode("utf-8", errors=errors)
        except UnicodeError:
            continue
        if _mojibake_score(repaired) < _mojibake_score(text) and _has_cyrillic(repaired):
            return repaired
    return text


def _mojibake_score(text: str) -> int:
    return sum(text.count(marker) for marker in ("Р ", "РЎ", "Гђ", "Г‘", "РІР‚"))


def _has_cyrillic(text: str) -> bool:
    return any("\u0400" <= char <= "\u04ff" for char in text)


def coerce_score(value: Any) -> float | None:
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def object_to_plain_data(value: Any) -> Any:
    for attr_name in ("json", "to_dict", "dict"):
        if not hasattr(value, attr_name):
            continue
        attr = getattr(value, attr_name)
        try:
            return attr() if callable(attr) else attr
        except Exception:
            continue
    if hasattr(value, "__dict__") and value.__class__.__module__.startswith("paddle"):
        return vars(value)
    return value


def collect_ocr_pairs(value: Any) -> list[OcrToken]:
    value = object_to_plain_data(value)
    pairs: list[OcrToken] = []

    if value is None:
        return pairs

    if isinstance(value, dict):
        if "res" in value:
            pairs.extend(collect_ocr_pairs(value["res"]))
        if "rec_texts" in value:
            texts = value.get("rec_texts") or []
            scores = value.get("rec_scores") or value.get("scores") or [None] * len(texts)
            for text, score in zip(texts, scores):
                cleaned = cleanup_text(text)
                if cleaned:
                    pairs.append(OcrToken(cleaned, coerce_score(score)))
            return pairs
        for text_key, score_key in (("rec_text", "rec_score"), ("text", "score")):
            if text_key in value:
                cleaned = cleanup_text(value.get(text_key))
                if cleaned:
                    pairs.append(OcrToken(cleaned, coerce_score(value.get(score_key) or value.get("confidence"))))
        for key, child in value.items():
            if key in {"res", "rec_texts", "rec_scores", "scores", "rec_text", "rec_score", "text", "score", "confidence"}:
                continue
            pairs.extend(collect_ocr_pairs(child))
        return pairs

    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[0], str):
            cleaned = cleanup_text(value[0])
            if cleaned:
                pairs.append(OcrToken(cleaned, coerce_score(value[1])))
            return pairs

        if (
            len(value) >= 2
            and isinstance(value[1], (list, tuple))
            and value[1]
            and isinstance(value[1][0], str)
        ):
            cleaned = cleanup_text(value[1][0])
            if cleaned:
                pairs.append(OcrToken(cleaned, coerce_score(value[1][1] if len(value[1]) > 1 else None)))
            return pairs

        for child in value:
            pairs.extend(collect_ocr_pairs(child))
    return pairs

