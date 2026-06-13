from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def detect_table_lines(
    binary: Any,
    horizontal_scale: int,
    vertical_scale: int,
) -> tuple[Any, Any, Any]:
    inverted = 255 - binary
    height, width = binary.shape[:2]

    horizontal_size = max(12, width // max(horizontal_scale, 1))
    vertical_size = max(12, height // max(vertical_scale, 1))

    horizontal_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (horizontal_size, 1))
    vertical_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, vertical_size))

    horizontal = cv2.erode(inverted, horizontal_kernel, iterations=1)
    horizontal = cv2.dilate(horizontal, horizontal_kernel, iterations=2)

    vertical = cv2.erode(inverted, vertical_kernel, iterations=1)
    vertical = cv2.dilate(vertical, vertical_kernel, iterations=2)

    grid = cv2.bitwise_or(horizontal, vertical)
    grid = cv2.morphologyEx(
        grid,
        cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 3)),
        iterations=1,
    )
    return horizontal, vertical, grid


def crop_to_table(image: Any, *masks: Any) -> tuple[Any, list[Any], tuple[int, int]]:
    combined = np.zeros(masks[0].shape[:2], dtype=np.uint8)
    for mask in masks:
        combined = cv2.bitwise_or(combined, mask)

    points = cv2.findNonZero(combined)
    if points is None:
        return image, list(masks), (0, 0)

    x, y, width, height = cv2.boundingRect(points)
    pad_x = max(8, width // 100)
    pad_y = max(8, height // 100)
    x1 = max(0, x - pad_x)
    y1 = max(0, y - pad_y)
    x2 = min(image.shape[1], x + width + pad_x)
    y2 = min(image.shape[0], y + height + pad_y)

    cropped_image = image[y1:y2, x1:x2].copy()
    cropped_masks = [mask[y1:y2, x1:x2].copy() for mask in masks]
    return cropped_image, cropped_masks, (x1, y1)

