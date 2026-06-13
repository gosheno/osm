from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def order_points(points: Any) -> Any:
    rect = np.zeros((4, 2), dtype="float32")
    summed = points.sum(axis=1)
    rect[0] = points[np.argmin(summed)]
    rect[2] = points[np.argmax(summed)]

    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def four_point_transform(image: Any, points: Any) -> Any:
    rect = order_points(points)
    top_left, top_right, bottom_right, bottom_left = rect

    width_a = np.linalg.norm(bottom_right - bottom_left)
    width_b = np.linalg.norm(top_right - top_left)
    max_width = max(int(width_a), int(width_b), 1)

    height_a = np.linalg.norm(top_right - bottom_right)
    height_b = np.linalg.norm(top_left - bottom_left)
    max_height = max(int(height_a), int(height_b), 1)

    destination = np.array(
        [
            [0, 0],
            [max_width - 1, 0],
            [max_width - 1, max_height - 1],
            [0, max_height - 1],
        ],
        dtype="float32",
    )
    matrix = cv2.getPerspectiveTransform(rect, destination)
    return cv2.warpPerspective(image, matrix, (max_width, max_height))


def find_document_contour(image: Any) -> Any | None:
    height = image.shape[0]
    if height <= 0:
        return None

    ratio = height / 700.0
    resized = cv2.resize(image, (max(1, int(image.shape[1] / ratio)), 700))
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(gray, 40, 140)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    contours = sorted(contours, key=cv2.contourArea, reverse=True)[:12]
    image_area = resized.shape[0] * resized.shape[1]

    for contour in contours:
        area = cv2.contourArea(contour)
        if area < image_area * 0.12:
            continue
        perimeter = cv2.arcLength(contour, True)
        approx = cv2.approxPolyDP(contour, 0.025 * perimeter, True)
        if len(approx) == 4:
            return approx.reshape(4, 2).astype("float32") * ratio
    return None


def perspective_correct(image: Any) -> tuple[Any, Any | None]:
    contour = find_document_contour(image)
    if contour is None:
        return image, None
    return four_point_transform(image, contour), contour

