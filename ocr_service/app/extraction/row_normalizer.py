from __future__ import annotations

from app.image_processing.cell_detection import Cell
from app.ocr_engines.base import cleanup_text


def normalize_cell_rows(cells: list[list[Cell]], *, drop_empty: bool = False) -> list[list[Cell]]:
    max_cols = max((len(row) for row in cells), default=0)
    normalized: list[list[Cell]] = []
    for row in cells:
        current = list(row)
        if drop_empty and not any(cleanup_text(cell.text) for cell in current):
            continue
        while len(current) < max_cols:
            col_index = len(current)
            current.append(Cell(row[0].row if row else len(normalized), col_index, 0, 0, 0, 0))
        normalized.append(current)
    return normalized

