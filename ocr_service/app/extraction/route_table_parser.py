from __future__ import annotations

from app.extraction.address_extractor import ExtractedRoutePoint, extract_route_point
from app.extraction.confidence import average_confidence
from app.image_processing.cell_detection import Cell
from app.ocr_engines.base import cleanup_text


def table_to_response(cells: list[list[Cell]]) -> dict[str, object]:
    rows = []
    max_cols = max((len(row) for row in cells), default=0)
    for row_index, row in enumerate(cells):
        confidences = [cell.confidence for cell in row]
        cell_payloads = [
            {
                "column_index": col_index,
                "text": cleanup_text(cell.text),
                "confidence": cell.confidence,
            }
            for col_index, cell in enumerate(row)
        ]
        rows.append(
            {
                "row_index": row_index,
                "cells": cell_payloads,
                "row_confidence": average_confidence(confidences),
                "raw_text": " | ".join(cell["text"] for cell in cell_payloads if cell["text"]),
            }
        )
    return {
        "rows_count": len(rows),
        "columns_count": max_cols,
        "rows": rows,
    }


def extract_route_points(cells: list[list[Cell]]) -> list[ExtractedRoutePoint]:
    route_points: list[ExtractedRoutePoint] = []
    for row_index, row in enumerate(cells):
        point = extract_route_point(
            row_index,
            [cell.text for cell in row],
            [cell.confidence for cell in row],
        )
        if point is not None:
            route_points.append(point)
    return route_points

