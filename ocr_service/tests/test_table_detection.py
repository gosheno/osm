from __future__ import annotations

import cv2
import numpy as np

from app.image_processing.cell_detection import detect_cells
from app.image_processing.table_detection import detect_table_lines


def test_detect_cells_from_synthetic_grid() -> None:
    binary = np.full((180, 300), 255, dtype=np.uint8)
    for x in (0, 100, 200, 299):
        cv2.line(binary, (x, 0), (x, 179), 0, 2)
    for y in (0, 60, 120, 179):
        cv2.line(binary, (0, y), (299, y), 0, 2)

    horizontal, vertical, grid = detect_table_lines(binary, 30, 30)
    cells, x_lines, y_lines = detect_cells(binary, horizontal, vertical, grid)

    assert len(x_lines) >= 4
    assert len(y_lines) >= 4
    assert len(cells) == 3
    assert all(len(row) == 3 for row in cells)

