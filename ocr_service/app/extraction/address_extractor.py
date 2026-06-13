from __future__ import annotations

import re
from dataclasses import dataclass, field

from app.ocr_engines.base import cleanup_text


ADDRESS_MARKERS = (
    "ул",
    "улица",
    "пр",
    "проспект",
    "пр-т",
    "шоссе",
    "наб",
    "набережная",
    "пер",
    "переулок",
    "пл",
    "площадь",
    "дом",
    "д.",
    "корп",
    "лит",
    "санкт-петербург",
    "спб",
    "ленинградская",
)
HEADER_MARKERS = ("адрес", "название", "магазин", "комментар", "номер", "order", "address", "name")


@dataclass(frozen=True)
class ExtractedRoutePoint:
    source_row_index: int
    original_order: int | None
    name: str | None
    address: str
    raw_row_text: str
    confidence: float
    warnings: list[dict[str, str]] = field(default_factory=list)


def extract_route_point(
    row_index: int,
    texts: list[str],
    confidences: list[float | None],
) -> ExtractedRoutePoint | None:
    cleaned = [cleanup_text(text) for text in texts]
    non_empty = [(index, text) for index, text in enumerate(cleaned) if text]
    if not non_empty:
        return None

    raw_row_text = " | ".join(text for _, text in non_empty)
    if _looks_like_header(raw_row_text):
        return None

    order = _extract_order(cleaned[0]) if cleaned else None
    address_index = _best_address_index(cleaned)
    if address_index is None:
        return None

    address = cleaned[address_index]
    if len(address) < 5:
        return None

    name = _extract_name(cleaned, address_index)
    confidence = _address_confidence(address, confidences[address_index] if address_index < len(confidences) else None)
    warnings: list[dict[str, str]] = []
    if confidence < 0.75:
        warnings.append(
            {
                "code": "LOW_CONFIDENCE_ADDRESS",
                "message": "Address was extracted with low confidence",
            }
        )
    if _address_score(address) < 2.0:
        warnings.append(
            {
                "code": "WEAK_ADDRESS_SIGNAL",
                "message": "Address markers are weak; row needs review",
            }
        )

    return ExtractedRoutePoint(
        source_row_index=row_index,
        original_order=order,
        name=name,
        address=address,
        raw_row_text=raw_row_text,
        confidence=confidence,
        warnings=warnings,
    )


def _looks_like_header(text: str) -> bool:
    lowered = text.lower()
    if any(marker in lowered for marker in HEADER_MARKERS):
        return not bool(re.search(r"\d", lowered) and "," in lowered)
    return False


def _extract_order(text: str) -> int | None:
    match = re.match(r"^\s*(?:#|№)?\s*(\d{1,4})\b", text or "")
    return int(match.group(1)) if match else None


def _best_address_index(texts: list[str]) -> int | None:
    scored = [(index, _address_score(text)) for index, text in enumerate(texts)]
    scored = [(index, score) for index, score in scored if score > 0]
    if not scored:
        return None
    return max(scored, key=lambda item: (item[1], len(texts[item[0]])))[0]


def _address_score(text: str) -> float:
    lowered = text.lower()
    if not lowered:
        return 0.0
    score = 0.0
    if "," in text:
        score += 1.0
    if re.search(r"\d", text):
        score += 1.0
    score += min(len(text), 80) / 80
    marker_hits = sum(1 for marker in ADDRESS_MARKERS if marker in lowered)
    score += min(marker_hits, 3) * 1.25
    if len(text.split()) < 2:
        score -= 1.0
    return score


def _extract_name(texts: list[str], address_index: int) -> str | None:
    candidates: list[str] = []
    for index, text in enumerate(texts):
        if index == address_index or not text:
            continue
        if _extract_order(text) is not None and len(text.split()) <= 2:
            continue
        if _address_score(text) >= _address_score(texts[address_index]):
            continue
        candidates.append(text)
    if not candidates:
        return None
    return max(candidates, key=len)


def _address_confidence(address: str, ocr_confidence: float | None) -> float:
    base = 0.62 if ocr_confidence is None else max(0.0, min(float(ocr_confidence), 0.99))
    signal_bonus = min(_address_score(address) / 10, 0.22)
    return round(max(0.0, min(base + signal_bonus, 0.99)), 4)

