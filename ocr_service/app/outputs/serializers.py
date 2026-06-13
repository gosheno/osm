from __future__ import annotations

from app.extraction.address_extractor import ExtractedRoutePoint


def route_point_to_dict(point: ExtractedRoutePoint) -> dict[str, object]:
    return {
        "source_row_index": point.source_row_index,
        "original_order": point.original_order,
        "name": point.name,
        "address": point.address,
        "raw_row_text": point.raw_row_text,
        "confidence": point.confidence,
        "warnings": point.warnings,
    }

