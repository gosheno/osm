from __future__ import annotations

import re
from dataclasses import dataclass
from difflib import SequenceMatcher

from app.services.address_extractor import SETTLEMENT_WORDS, extract_delivery_record
from app.services.ocr_service import OcrResult


@dataclass(frozen=True)
class ParsedRouteSheetRow:
    row_number: int
    raw_ocr_text: str
    store_name: str | None
    address: str
    confidence_score: float


class RouteSheetParser:
    def parse(self, ocr_result: OcrResult, *, row_offset: int = 0) -> list[ParsedRouteSheetRow]:
        if ocr_result.route_points:
            return _dedupe_similar_rows(
                [
                    ParsedRouteSheetRow(
                        row_number=row_offset + index,
                        raw_ocr_text=point.raw_row_text or point.address,
                        store_name=point.name,
                        address=point.address,
                        confidence_score=_safe_confidence(point.confidence),
                    )
                    for index, point in enumerate(ocr_result.route_points, start=1)
                ],
                row_offset=row_offset,
            )

        rows: list[ParsedRouteSheetRow] = []
        seen_addresses: set[str] = set()
        lines = [line.text for line in ocr_result.lines if line.text.strip()]

        for index, line in enumerate(lines):
            previous_line = lines[index - 1] if index > 0 else None
            extracted = extract_delivery_record(line, previous_line=previous_line)
            if extracted is None:
                continue
            key = _address_key(extracted.address)
            if key in seen_addresses:
                continue
            seen_addresses.add(key)
            rows.append(
                ParsedRouteSheetRow(
                    row_number=row_offset + len(rows) + 1,
                    raw_ocr_text=extracted.raw_text,
                    store_name=extracted.store_name,
                    address=extracted.address,
                    confidence_score=extracted.confidence_score,
                )
            )

        if not rows and ocr_result.raw_text:
            rows.extend(self._parse_from_joined_text(ocr_result.raw_text, row_offset=row_offset))

        return _dedupe_similar_rows(rows, row_offset=row_offset)

    def _parse_from_joined_text(self, raw_text: str, *, row_offset: int) -> list[ParsedRouteSheetRow]:
        rows: list[ParsedRouteSheetRow] = []
        parts = [part.strip() for part in raw_text.replace("\t", "\n").splitlines() if part.strip()]
        previous_line: str | None = None
        for part in parts:
            extracted = extract_delivery_record(part, previous_line=previous_line)
            if extracted is not None:
                rows.append(
                    ParsedRouteSheetRow(
                        row_number=row_offset + len(rows) + 1,
                        raw_ocr_text=extracted.raw_text,
                        store_name=extracted.store_name,
                        address=extracted.address,
                        confidence_score=extracted.confidence_score,
                    )
                )
            previous_line = part
        return rows


def _address_key(address: str) -> str:
    return " ".join((address or "").lower().replace(".", "").split())


def _dedupe_similar_rows(
    rows: list[ParsedRouteSheetRow],
    *,
    row_offset: int,
) -> list[ParsedRouteSheetRow]:
    filtered = [row for row in rows if not _looks_like_fragment(row.address)]
    result: list[ParsedRouteSheetRow] = []
    for row in filtered:
        duplicate_index = next(
            (index for index, existing in enumerate(result) if _same_ocr_address(existing.address, row.address)),
            None,
        )
        if duplicate_index is None:
            result.append(row)
            continue
        if _row_quality(row) > _row_quality(result[duplicate_index]):
            result[duplicate_index] = row

    return [
        ParsedRouteSheetRow(
            row_number=row_offset + index,
            raw_ocr_text=row.raw_ocr_text,
            store_name=row.store_name,
            address=row.address,
            confidence_score=row.confidence_score,
        )
        for index, row in enumerate(result, start=1)
    ]


def _looks_like_fragment(address: str) -> bool:
    normalized = (address or "").strip(" .,;-").lower()
    if not normalized:
        return True
    first = normalized.split()[0].strip(" .,;-")
    if first in {"а", "в", "и", "ул", "кая", "ков", "срое"}:
        return True
    if normalized.startswith(("ыкников ", ". ", "- ", "в пр", "а хвал")):
        return True
    if len(first) <= 2 and "," not in normalized:
        return True
    return False


def _same_ocr_address(left: str, right: str) -> bool:
    left_key = _canonical_key(left)
    right_key = _canonical_key(right)
    if left_key == right_key:
        return True

    left_house = _house_number(left_key)
    right_house = _house_number(right_key)
    if left_house and right_house and left_house == right_house:
        shorter, longer = sorted((left_key, right_key), key=len)
        if len(shorter) >= 10 and shorter in longer:
            return True
        return SequenceMatcher(None, left_key, right_key).ratio() >= 0.86
    return False


def _canonical_key(address: str) -> str:
    value = (address or "").lower().replace("ё", "е")
    value = re.sub(r"\b(?:ул|улица)\b\.?", "улица", value)
    value = re.sub(r"\b(?:пр|проспект)\b\.?", "проспект", value)
    value = re.sub(r"\b(?:ш|шоссе)\b\.?", "шоссе", value)
    value = re.sub(r"[^0-9a-zа-я/]+", " ", value)
    return " ".join(value.split())


def _house_number(value: str) -> str | None:
    matches = re.findall(r"\d+[0-9a-zа-я/.-]*", value.lower())
    return matches[-1] if matches else None


def _row_quality(row: ParsedRouteSheetRow) -> float:
    address = row.address
    score = row.confidence_score
    if "," in address:
        score += 0.15
    if any(word.lower() in address.lower() for word in SETTLEMENT_WORDS):
        score += 0.15
    score += min(len(address), 80) / 1000
    return score


def _safe_confidence(value: float | None) -> float:
    try:
        if value is None:
            return 0.65
        return max(0.0, min(float(value), 0.99))
    except (TypeError, ValueError):
        return 0.65
