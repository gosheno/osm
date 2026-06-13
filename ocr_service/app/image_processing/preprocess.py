from __future__ import annotations

from typing import Any

import cv2
import numpy as np


def preprocess_for_ocr(image: Any, line_mode: str) -> tuple[dict[str, Any], Any]:
    stages: dict[str, Any] = {}

    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    stages["02_gray"] = gray

    clahe = cv2.createCLAHE(clipLimit=1.4, tileGridSize=(8, 8)).apply(gray)
    stages["03_mild_clahe"] = clahe

    denoised = cv2.fastNlMeansDenoising(clahe, None, h=5, templateWindowSize=7)
    stages["04_mild_denoised"] = denoised

    blur = cv2.GaussianBlur(denoised, (0, 0), 1.0)
    sharpened = cv2.addWeighted(denoised, 1.25, blur, -0.25, 0)
    stages["05_mild_sharpened"] = sharpened

    block_size = max(31, (min(image.shape[:2]) // 25) | 1)
    if block_size % 2 == 0:
        block_size += 1
    soft_binary = cv2.adaptiveThreshold(
        sharpened,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        13,
    )
    if np.mean(soft_binary) < 127:
        soft_binary = 255 - soft_binary
    stages["06_soft_binary_for_line_detection"] = soft_binary

    if line_mode == "soft":
        return stages, soft_binary

    bg_kernel = np.ones((7, 7), np.uint8)
    background = cv2.medianBlur(cv2.dilate(clahe, bg_kernel, iterations=1), 31)
    line_normalized = 255 - cv2.absdiff(clahe, background)
    line_normalized = cv2.normalize(line_normalized, None, 0, 255, cv2.NORM_MINMAX)
    stages["07_line_shadow_normalized"] = line_normalized

    aggressive_binary = cv2.adaptiveThreshold(
        line_normalized,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        block_size,
        13,
    )
    if np.mean(aggressive_binary) < 127:
        aggressive_binary = 255 - aggressive_binary
    stages["08_aggressive_binary_for_line_detection"] = aggressive_binary
    return stages, aggressive_binary


def preprocess_cell(cell_image: Any, mode: str, *, as_bgr: bool) -> Any:
    if mode == "raw":
        prepared = (
            cv2.cvtColor(cell_image, cv2.COLOR_GRAY2BGR)
            if len(cell_image.shape) == 2
            else cell_image.copy()
        )
        return cv2.copyMakeBorder(
            prepared, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=(255, 255, 255)
        )

    gray = cv2.cvtColor(cell_image, cv2.COLOR_BGR2GRAY) if len(cell_image.shape) == 3 else cell_image
    gray = cv2.copyMakeBorder(gray, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255)
    gray = cv2.bilateralFilter(gray, 5, 35, 35)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    scale = 2 if max(gray.shape[:2]) > 140 else 3
    enlarged = cv2.resize(gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
    enhanced = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(enlarged)
    blur = cv2.GaussianBlur(enhanced, (0, 0), 0.8)
    enhanced = cv2.addWeighted(enhanced, 1.2, blur, -0.2, 0)

    if mode == "gray":
        return cv2.cvtColor(enhanced, cv2.COLOR_GRAY2BGR) if as_bgr else enhanced

    binary = cv2.adaptiveThreshold(
        enlarged,
        255,
        cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
        cv2.THRESH_BINARY,
        35,
        11,
    )
    if np.mean(binary) < 127:
        binary = 255 - binary

    if mode == "binary":
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR) if as_bgr else binary

    prepared = binary if float(np.std(enhanced)) < 28 else enhanced
    return cv2.cvtColor(prepared, cv2.COLOR_GRAY2BGR) if as_bgr else prepared

