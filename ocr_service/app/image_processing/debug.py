from __future__ import annotations

import base64
from typing import Any

import cv2

from app.image_processing.cell_detection import Cell


def image_to_base64_png(image: Any) -> str:
    ok, encoded = cv2.imencode(".png", image)
    if not ok:
        raise RuntimeError("Could not encode debug image")
    return base64.b64encode(encoded.tobytes()).decode("ascii")


def artifact(name: str, image: Any) -> dict[str, str]:
    return {
        "name": name,
        "type": "image/png",
        "base64": image_to_base64_png(image),
    }


def draw_cell_overlay(
    image: Any,
    cells: list[list[Cell]],
    *,
    include_text: bool = False,
) -> Any:
    overlay = image.copy()
    for row in cells:
        for cell in row:
            cv2.rectangle(overlay, (cell.x1, cell.y1), (cell.x2, cell.y2), (0, 190, 0), 2)
            label = f"{cell.row + 1}:{cell.col + 1}"
            if include_text and cell.text:
                label += " " + cell.text[:24]
            cv2.putText(
                overlay,
                label,
                (cell.x1 + 3, max(cell.y1 + 14, 14)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.38,
                (0, 0, 220),
                1,
                cv2.LINE_AA,
            )
    return overlay

