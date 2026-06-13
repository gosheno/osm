from __future__ import annotations

import cv2
import numpy as np

from app.core.pipeline import process_debug_table


def test_debug_table_returns_artifacts_for_synthetic_grid() -> None:
    image = np.full((180, 300, 3), 255, dtype=np.uint8)
    for x in (0, 100, 200, 299):
        cv2.line(image, (x, 0), (x, 179), (0, 0, 0), 2)
    for y in (0, 60, 120, 179):
        cv2.line(image, (0, y), (299, y), (0, 0, 0), 2)
    ok, encoded = cv2.imencode(".png", image)
    assert ok

    payload = process_debug_table("table.png", encoded.tobytes())

    assert payload["status"] == "ok"
    assert payload["table_detected"] is True
    assert payload["rows_count"] == 3
    assert payload["columns_count"] == 3
    assert payload["debug_artifacts"]

