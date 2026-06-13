from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import cv2
import numpy as np


@dataclass
class Cell:
    row: int
    col: int
    x1: int
    y1: int
    x2: int
    y2: int
    text: str = ""
    confidence: float | None = None


def projection_centers(
    mask: Any,
    orientation: str,
    min_coverage_ratio: float = 0.06,
    merge_gap: int = 4,
) -> list[int]:
    if orientation == "vertical":
        projection = np.count_nonzero(mask > 0, axis=0)
        long_side = mask.shape[0]
    else:
        projection = np.count_nonzero(mask > 0, axis=1)
        long_side = mask.shape[1]

    threshold = max(3, int(long_side * min_coverage_ratio))
    indices = np.where(projection >= threshold)[0]
    if indices.size == 0:
        nonzero = projection[projection > 0]
        if nonzero.size == 0:
            return []
        threshold = max(2, int(np.percentile(nonzero, 70)))
        indices = np.where(projection >= threshold)[0]
    if indices.size == 0:
        return []

    groups: list[list[int]] = []
    current = [int(indices[0])]
    for value in indices[1:]:
        value = int(value)
        if value - current[-1] <= merge_gap:
            current.append(value)
        else:
            groups.append(current)
            current = [value]
    groups.append(current)
    return [int(round(sum(group) / len(group))) for group in groups]


def dedupe_sorted(values: list[int], min_distance: int) -> list[int]:
    if not values:
        return []
    values = sorted(values)
    deduped = [values[0]]
    for value in values[1:]:
        if value - deduped[-1] >= min_distance:
            deduped.append(value)
        else:
            deduped[-1] = int(round((deduped[-1] + value) / 2))
    return deduped


def add_border_lines(lines: list[int], limit: int, tolerance: int = 14) -> list[int]:
    if not lines:
        return [0, limit - 1]
    result = list(lines)
    if result[0] > tolerance:
        result.insert(0, 0)
    if (limit - 1) - result[-1] > tolerance:
        result.append(limit - 1)
    return result


def cells_from_lines(
    x_lines: list[int],
    y_lines: list[int],
    min_cell_width: int = 10,
    min_cell_height: int = 10,
) -> list[list[Cell]]:
    rows: list[list[Cell]] = []
    row_index = 0
    for r in range(len(y_lines) - 1):
        y1, y2 = y_lines[r], y_lines[r + 1]
        if y2 - y1 < min_cell_height:
            continue
        row_cells: list[Cell] = []
        col_index = 0
        for c in range(len(x_lines) - 1):
            x1, x2 = x_lines[c], x_lines[c + 1]
            if x2 - x1 < min_cell_width:
                continue
            row_cells.append(Cell(row_index, col_index, x1, y1, x2, y2))
            col_index += 1
        if row_cells:
            rows.append(row_cells)
            row_index += 1
    return rows


def contour_cells_fallback(grid: Any) -> list[list[Cell]]:
    contours, _ = cv2.findContours(grid, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    boxes: list[tuple[int, int, int, int]] = []
    height, width = grid.shape[:2]
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = w * h
        if w < 10 or h < 10:
            continue
        if area > width * height * 0.85:
            continue
        if area < 80:
            continue
        boxes.append((x, y, x + w, y + h))

    boxes = sorted(boxes, key=lambda box: (box[1], box[0]))
    rows: list[list[Cell]] = []
    for x1, y1, x2, y2 in boxes:
        placed = False
        for row in rows:
            ry1 = row[0].y1
            ry2 = row[0].y2
            if abs(y1 - ry1) <= max(8, (ry2 - ry1) // 2):
                row.append(Cell(len(rows) - 1, len(row), x1, y1, x2, y2))
                placed = True
                break
        if not placed:
            rows.append([Cell(len(rows), 0, x1, y1, x2, y2)])

    for row_index, row in enumerate(rows):
        row.sort(key=lambda cell: cell.x1)
        for col_index, cell in enumerate(row):
            cell.row = row_index
            cell.col = col_index
    return rows


def detect_cells(
    table_binary: Any,
    horizontal: Any,
    vertical: Any,
    grid: Any,
    *,
    min_cell_width: int = 8,
    min_cell_height: int = 8,
    merge_gap: int = 4,
) -> tuple[list[list[Cell]], list[int], list[int]]:
    height, width = table_binary.shape[:2]
    x_lines = projection_centers(
        vertical,
        "vertical",
        min_coverage_ratio=0.06,
        merge_gap=merge_gap,
    )
    y_lines = projection_centers(
        horizontal,
        "horizontal",
        min_coverage_ratio=0.25,
        merge_gap=merge_gap,
    )

    x_lines = dedupe_sorted(x_lines, min_distance=max(5, width // 250))
    y_lines = dedupe_sorted(y_lines, min_distance=max(5, height // 250))
    x_lines = add_border_lines(x_lines, width, tolerance=max(14, width // 80))
    y_lines = add_border_lines(y_lines, height, tolerance=max(14, height // 80))

    cells = cells_from_lines(
        x_lines,
        y_lines,
        min_cell_width=max(min_cell_width, width // 180),
        min_cell_height=max(min_cell_height, height // 220),
    )
    if len(cells) < 2 or max((len(row) for row in cells), default=0) < 2:
        cells = contour_cells_fallback(grid)
    return cells, x_lines, y_lines

