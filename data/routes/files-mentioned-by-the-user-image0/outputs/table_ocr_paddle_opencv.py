from __future__ import annotations

import argparse
import csv
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


cv2: Any = None
np: Any = None
PaddleOCR: Any = None
TextRecognition: Any = None
pd: Any = None

os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")


@dataclass
class Cell:
    row: int
    col: int
    x1: int
    y1: int
    x2: int
    y2: int
    text: str = ""
    confidence: float = -1.0


def ensure_dependencies(require_paddle: bool) -> None:
    global cv2, np, PaddleOCR, TextRecognition, pd

    missing = []
    try:
        import cv2 as _cv2
    except ImportError:
        missing.append("opencv-python")
    else:
        cv2 = _cv2

    try:
        import numpy as _np
    except ImportError:
        missing.append("numpy")
    else:
        np = _np

    if require_paddle:
        if importlib.util.find_spec("paddle") is None:
            missing.append("paddlepaddle")
        if importlib.util.find_spec("paddleocr") is None:
            missing.append("paddleocr")

    if (
        require_paddle
        and "paddlepaddle" not in missing
        and "paddleocr" not in missing
    ):
        try:
            from paddleocr import PaddleOCR as _PaddleOCR
            from paddleocr import TextRecognition as _TextRecognition
        except Exception as exc:
            raise SystemExit(
                "Could not import PaddleOCR. Check your paddlepaddle/paddleocr "
                f"installation.\nOriginal error: {exc}"
            ) from exc
        else:
            PaddleOCR = _PaddleOCR
            TextRecognition = _TextRecognition

    try:
        import pandas as _pd
    except Exception:
        pd = None
    else:
        pd = _pd

    if missing:
        raise SystemExit(
            "Missing Python packages: "
            + ", ".join(missing)
            + "\nInstall them with:\n"
            + "  python -m pip install paddlepaddle "
            + "-i https://www.paddlepaddle.org.cn/packages/stable/cpu/\n"
            + '  python -m pip install "paddleocr[all]" opencv-python '
            + "numpy pandas openpyxl\n"
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Extract a photographed table with OpenCV + PaddleOCR and save the "
            "recognized table plus preprocessing debug images."
        )
    )
    parser.add_argument("--image", required=True, help="Path to the source photo.")
    parser.add_argument(
        "--output-dir",
        default="ocr_output",
        help="Directory for CSV/XLSX/HTML and debug images.",
    )
    parser.add_argument(
        "--lang",
        default="ru",
        help=(
            "PaddleOCR language code. For Russian try ru first; if your "
            "installed PaddleOCR build does not support it, try cyrillic."
        ),
    )
    parser.add_argument(
        "--use-gpu",
        action="store_true",
        help="Use GPU if PaddlePaddle with CUDA is installed.",
    )
    parser.add_argument(
        "--min-score",
        type=float,
        default=0.35,
        help="Minimal PaddleOCR text score used when joining OCR tokens.",
    )
    parser.add_argument(
        "--paddle-engine",
        choices=("recognition", "pipeline"),
        default="recognition",
        help=(
            "recognition uses PaddleOCR TextRecognition on already detected "
            "cells; pipeline uses the full PaddleOCR detector+recognizer."
        ),
    )
    parser.add_argument(
        "--recognition-model",
        default="auto",
        help=(
            "Paddle TextRecognition model. auto uses eslav_PP-OCRv5_mobile_rec "
            "for --lang ru; pass none to use PaddleOCR default."
        ),
    )
    parser.add_argument(
        "--max-side",
        type=int,
        default=2600,
        help="Resize large photos before processing; 0 disables resizing.",
    )
    parser.add_argument(
        "--horizontal-scale",
        type=int,
        default=35,
        help=(
            "Horizontal line kernel divisor. Smaller value finds longer/stronger "
            "lines; larger value keeps shorter broken lines."
        ),
    )
    parser.add_argument(
        "--vertical-scale",
        type=int,
        default=35,
        help=(
            "Vertical line kernel divisor. Smaller value finds longer/stronger "
            "lines; larger value keeps shorter broken lines."
        ),
    )
    parser.add_argument(
        "--show",
        action="store_true",
        help="Show preprocessing stages and detected cells in OpenCV windows.",
    )
    parser.add_argument(
        "--cell-mode",
        choices=("raw", "gray", "binary", "auto"),
        default="raw",
        help=(
            "How to prepare each cell for PaddleOCR. raw keeps the original "
            "crop and is the default; gray is mildly enhanced; binary is more "
            "aggressive; auto picks by cell contrast."
        ),
    )
    parser.add_argument(
        "--line-mode",
        choices=("aggressive", "soft"),
        default="aggressive",
        help=(
            "How to build the table-line mask. aggressive is better for warped "
            "photos with shadows; soft is less destructive but may miss lines."
        ),
    )
    parser.add_argument(
        "--skip-ocr",
        action="store_true",
        help="Only detect/preprocess table cells; do not run PaddleOCR.",
    )
    parser.add_argument(
        "--no-debug",
        action="store_true",
        help="Do not save preprocessing/debug images.",
    )
    parser.add_argument(
        "--drop-empty-rows",
        action="store_true",
        help="Remove rows where every recognized cell is empty.",
    )
    parser.add_argument(
        "--first-row-header",
        action="store_true",
        help="Use the first OCR row as a header in Markdown output.",
    )
    return parser.parse_args()


def imread_unicode(path: Path) -> Any:
    if not path.exists():
        raise SystemExit(f"Image was not found: {path}")
    data = np.fromfile(str(path), dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise SystemExit(f"Could not read image: {path}")
    return image


def imwrite_unicode(path: Path, image: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    ext = path.suffix or ".png"
    ok, encoded = cv2.imencode(ext, image)
    if not ok:
        raise RuntimeError(f"Could not encode image for saving: {path}")
    encoded.tofile(str(path))


def resize_max_side(image: Any, max_side: int) -> Any:
    if max_side <= 0:
        return image
    height, width = image.shape[:2]
    scale = max_side / float(max(height, width))
    if scale >= 1.0:
        return image
    new_size = (int(width * scale), int(height * scale))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA)


def order_points(points: Any) -> Any:
    rect = np.zeros((4, 2), dtype="float32")
    s = points.sum(axis=1)
    rect[0] = points[np.argmin(s)]
    rect[2] = points[np.argmax(s)]

    diff = np.diff(points, axis=1)
    rect[1] = points[np.argmin(diff)]
    rect[3] = points[np.argmax(diff)]
    return rect


def four_point_transform(image: Any, points: Any) -> Any:
    rect = order_points(points)
    top_left, top_right, bottom_right, bottom_left = rect

    width_a = np.linalg.norm(bottom_right - bottom_left)
    width_b = np.linalg.norm(top_right - top_left)
    max_width = max(int(width_a), int(width_b))

    height_a = np.linalg.norm(top_right - bottom_right)
    height_b = np.linalg.norm(top_left - bottom_left)
    max_height = max(int(height_a), int(height_b))

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
    ratio = image.shape[0] / 700.0
    resized = cv2.resize(image, (int(image.shape[1] / ratio), 700))
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
    warped = four_point_transform(image, contour)
    return warped, contour


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
    line_normalized = cv2.normalize(
        line_normalized, None, 0, 255, cv2.NORM_MINMAX
    )
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
    binary = aggressive_binary
    return stages, binary


def detect_table_lines(
    binary: Any, horizontal_scale: int, vertical_scale: int
) -> tuple[Any, Any, Any]:
    inverted = 255 - binary
    height, width = binary.shape[:2]

    horizontal_size = max(12, width // max(horizontal_scale, 1))
    vertical_size = max(12, height // max(vertical_scale, 1))

    horizontal_kernel = cv2.getStructuringElement(
        cv2.MORPH_RECT, (horizontal_size, 1)
    )
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

    centers = [int(round(sum(group) / len(group))) for group in groups]
    return centers


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

    boxes = sorted(boxes, key=lambda b: (b[1], b[0]))
    rows: list[list[Cell]] = []
    for box in boxes:
        x1, y1, x2, y2 = box
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
) -> tuple[list[list[Cell]], list[int], list[int]]:
    height, width = table_binary.shape[:2]
    x_lines = projection_centers(vertical, "vertical", min_coverage_ratio=0.06)
    y_lines = projection_centers(horizontal, "horizontal", min_coverage_ratio=0.25)

    x_lines = dedupe_sorted(x_lines, min_distance=max(5, width // 250))
    y_lines = dedupe_sorted(y_lines, min_distance=max(5, height // 250))
    x_lines = add_border_lines(x_lines, width, tolerance=max(14, width // 80))
    y_lines = add_border_lines(y_lines, height, tolerance=max(14, height // 80))

    cells = cells_from_lines(
        x_lines,
        y_lines,
        min_cell_width=max(8, width // 180),
        min_cell_height=max(8, height // 220),
    )

    if len(cells) < 2 or max((len(row) for row in cells), default=0) < 2:
        cells = contour_cells_fallback(grid)
    return cells, x_lines, y_lines


def preprocess_cell_for_paddle(cell_image: Any, mode: str) -> Any:
    if mode == "raw":
        if len(cell_image.shape) == 2:
            prepared = cv2.cvtColor(cell_image, cv2.COLOR_GRAY2BGR)
        else:
            prepared = cell_image.copy()
        return cv2.copyMakeBorder(
            prepared, 3, 3, 3, 3, cv2.BORDER_CONSTANT, value=(255, 255, 255)
        )

    if len(cell_image.shape) == 3:
        gray = cv2.cvtColor(cell_image, cv2.COLOR_BGR2GRAY)
    else:
        gray = cell_image

    gray = cv2.copyMakeBorder(
        gray, 8, 8, 8, 8, cv2.BORDER_CONSTANT, value=255
    )
    gray = cv2.bilateralFilter(gray, 5, 35, 35)
    gray = cv2.normalize(gray, None, 0, 255, cv2.NORM_MINMAX)

    scale = 2 if max(gray.shape[:2]) > 140 else 3
    enlarged = cv2.resize(
        gray, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC
    )
    enhanced = cv2.createCLAHE(clipLimit=1.6, tileGridSize=(8, 8)).apply(enlarged)
    blur = cv2.GaussianBlur(enhanced, (0, 0), 0.8)
    enhanced = cv2.addWeighted(enhanced, 1.2, blur, -0.2, 0)

    if mode == "gray":
        prepared = enhanced
        return cv2.cvtColor(prepared, cv2.COLOR_GRAY2BGR)

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
        return cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR)

    contrast = float(np.std(enhanced))
    prepared = binary if contrast < 28 else enhanced
    return cv2.cvtColor(prepared, cv2.COLOR_GRAY2BGR)


def cleanup_text(text: str) -> str:
    text = text.replace("\n", " ").replace("\r", " ")
    text = text.replace("|", "I")
    return " ".join(text.split()).strip()


def coerce_score(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def object_to_plain_data(value: Any) -> Any:
    for attr_name in ("json", "to_dict", "dict"):
        if not hasattr(value, attr_name):
            continue
        attr = getattr(value, attr_name)
        try:
            return attr() if callable(attr) else attr
        except Exception:
            continue
    if hasattr(value, "__dict__") and value.__class__.__module__.startswith(
        "paddle"
    ):
        return vars(value)
    return value


def collect_ocr_pairs(value: Any) -> list[tuple[str, float | None]]:
    value = object_to_plain_data(value)
    pairs: list[tuple[str, float | None]] = []

    if value is None:
        return pairs

    if isinstance(value, dict):
        if "res" in value:
            pairs.extend(collect_ocr_pairs(value["res"]))
        if "rec_texts" in value:
            texts = value.get("rec_texts") or []
            scores = (
                value.get("rec_scores")
                or value.get("scores")
                or [None] * len(texts)
            )
            for text, score in zip(texts, scores):
                text = cleanup_text(str(text))
                if text:
                    pairs.append((text, coerce_score(score)))
            return pairs
        if "rec_text" in value:
            text = cleanup_text(str(value.get("rec_text") or ""))
            score = coerce_score(value.get("rec_score") or value.get("score"))
            if text:
                pairs.append((text, score))
        if "text" in value:
            text = cleanup_text(str(value.get("text") or ""))
            score = coerce_score(value.get("score") or value.get("confidence"))
            if text:
                pairs.append((text, score))
        for key, child in value.items():
            if key in {
                "res",
                "rec_texts",
                "rec_scores",
                "rec_text",
                "rec_score",
                "text",
                "score",
                "confidence",
            }:
                continue
            pairs.extend(collect_ocr_pairs(child))
        return pairs

    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and isinstance(value[0], str):
            text = cleanup_text(value[0])
            if text:
                pairs.append((text, coerce_score(value[1])))
            return pairs

        if (
            len(value) >= 2
            and isinstance(value[1], (list, tuple))
            and value[1]
            and isinstance(value[1][0], str)
        ):
            text = cleanup_text(value[1][0])
            if text:
                score = value[1][1] if len(value[1]) > 1 else None
                pairs.append((text, coerce_score(score)))
            return pairs

        for child in value:
            pairs.extend(collect_ocr_pairs(child))
        return pairs

    return pairs


class PaddleOcrEngine:
    def __init__(
        self,
        lang: str,
        use_gpu: bool,
        min_score: float,
        paddle_engine: str,
        recognition_model: str,
    ) -> None:
        self.min_score = min_score
        self.paddle_engine = paddle_engine
        if paddle_engine == "recognition":
            self.ocr = self._create_recognition_engine(lang, recognition_model)
        else:
            self.ocr = self._create_pipeline_engine(lang, use_gpu)

    @staticmethod
    def _auto_recognition_model(lang: str, recognition_model: str) -> str | None:
        if recognition_model.lower() == "none":
            return None
        if recognition_model != "auto":
            return recognition_model
        if lang.lower() in {"ru", "rus", "russian"}:
            return "eslav_PP-OCRv5_mobile_rec"
        return None

    @classmethod
    def _create_recognition_engine(
        cls, lang: str, recognition_model: str
    ) -> Any:
        model_name = cls._auto_recognition_model(lang, recognition_model)
        kwargs = {"model_name": model_name} if model_name else {}
        try:
            return TextRecognition(**kwargs)
        except Exception as exc:
            raise SystemExit(
                "Could not initialize PaddleOCR TextRecognition.\n"
                "For Russian try: --recognition-model eslav_PP-OCRv5_mobile_rec\n"
                f"Original error: {exc}"
            ) from exc

    @staticmethod
    def _create_pipeline_engine(lang: str, use_gpu: bool) -> Any:
        attempts: list[dict[str, Any]] = [
            {
                "lang": lang,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "use_gpu": use_gpu,
            },
            {
                "lang": lang,
                "use_doc_orientation_classify": False,
                "use_doc_unwarping": False,
                "use_textline_orientation": False,
                "device": "gpu:0" if use_gpu else "cpu",
            },
            {"lang": lang},
        ]
        errors: list[str] = []
        for kwargs in attempts:
            try:
                return PaddleOCR(**kwargs)
            except TypeError as exc:
                errors.append(f"{kwargs}: {exc}")
            except Exception as exc:
                errors.append(f"{kwargs}: {exc}")

        raise SystemExit(
            "Could not initialize PaddleOCR.\n"
            "Try another language code, for example --lang cyrillic.\n"
            "Initialization errors:\n  "
            + "\n  ".join(errors[-3:])
        )

    def recognize(self, image: Any) -> tuple[str, float]:
        raw_result = self._run_ocr(image)
        pairs = collect_ocr_pairs(raw_result)

        texts: list[str] = []
        scores: list[float] = []
        for text, score in pairs:
            if score is None or score >= self.min_score:
                texts.append(text)
                if score is not None:
                    scores.append(score)

        text = cleanup_text(" ".join(texts))
        confidence = sum(scores) / len(scores) if scores else -1.0
        return text, confidence

    def _run_ocr(self, image: Any) -> Any:
        errors: list[str] = []

        if self.paddle_engine == "recognition":
            for kwargs in ({"input": image}, {}):
                try:
                    return self.ocr.predict(**kwargs)
                except TypeError as exc:
                    errors.append(f"predict kwargs={kwargs}: {exc}")
                except Exception as exc:
                    errors.append(f"predict kwargs={kwargs}: {exc}")

        if hasattr(self.ocr, "ocr"):
            for kwargs in ({"cls": True}, {}):
                try:
                    return self.ocr.ocr(image, **kwargs)
                except TypeError as exc:
                    errors.append(f"ocr kwargs={kwargs}: {exc}")
                except Exception as exc:
                    errors.append(f"ocr kwargs={kwargs}: {exc}")

        if hasattr(self.ocr, "predict"):
            for kwargs in ({"input": image}, {}):
                try:
                    return self.ocr.predict(**kwargs)
                except TypeError as exc:
                    errors.append(f"predict kwargs={kwargs}: {exc}")
                except Exception as exc:
                    errors.append(f"predict kwargs={kwargs}: {exc}")

        raise RuntimeError("PaddleOCR failed: " + " | ".join(errors[-4:]))


def ocr_cell(
    table_image: Any,
    cell: Cell,
    engine: PaddleOcrEngine,
    cell_mode: str,
) -> tuple[str, float]:
    width = cell.x2 - cell.x1
    height = cell.y2 - cell.y1
    if cell_mode == "raw":
        pad_x = 1
        pad_y = 1
    else:
        pad_x = min(max(3, width // 18), 10)
        pad_y = min(max(3, height // 18), 10)

    x1 = min(max(cell.x1 + pad_x, 0), table_image.shape[1] - 1)
    y1 = min(max(cell.y1 + pad_y, 0), table_image.shape[0] - 1)
    x2 = max(min(cell.x2 - pad_x, table_image.shape[1]), x1 + 1)
    y2 = max(min(cell.y2 - pad_y, table_image.shape[0]), y1 + 1)
    roi = table_image[y1:y2, x1:x2]

    if roi.size == 0:
        return "", -1.0

    prepared = preprocess_cell_for_paddle(roi, cell_mode)
    return engine.recognize(prepared)


def recognize_cells(
    table_image: Any,
    cells: list[list[Cell]],
    engine: PaddleOcrEngine,
    cell_mode: str,
) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in cells:
        values: list[str] = []
        for cell in row:
            text, confidence = ocr_cell(table_image, cell, engine, cell_mode)
            cell.text = text
            cell.confidence = confidence
            values.append(text)
        rows.append(values)
    return rows


def draw_cell_overlay(
    image: Any,
    cells: list[list[Cell]],
    include_text: bool = False,
) -> Any:
    overlay = image.copy()
    for row in cells:
        for cell in row:
            cv2.rectangle(
                overlay,
                (cell.x1, cell.y1),
                (cell.x2, cell.y2),
                (0, 190, 0),
                2,
            )
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


def normalize_rows(rows: list[list[str]]) -> list[list[str]]:
    max_cols = max((len(row) for row in rows), default=0)
    return [row + [""] * (max_cols - len(row)) for row in rows]


def drop_empty_rows(rows: list[list[str]]) -> list[list[str]]:
    return [row for row in rows if any(cell.strip() for cell in row)]


def write_table_outputs(rows: list[list[str]], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = normalize_rows(rows)

    csv_path = output_dir / "ocr_table.csv"
    with csv_path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerows(rows)

    tsv_path = output_dir / "ocr_table.tsv"
    with tsv_path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file, delimiter="\t")
        writer.writerows(rows)

    if pd is not None:
        df = pd.DataFrame(rows)
        html = df.to_html(index=False, header=False, escape=True)
        (output_dir / "ocr_table.html").write_text(html, encoding="utf-8")
        try:
            df.to_excel(output_dir / "ocr_table.xlsx", index=False, header=False)
        except Exception as exc:
            print(f"Warning: XLSX was not written: {exc}", file=sys.stderr)


def markdown_table(rows: list[list[str]], first_row_header: bool) -> str:
    rows = normalize_rows(rows)
    if not rows:
        return ""

    def escape(value: str) -> str:
        return value.replace("|", "\\|")

    if first_row_header and len(rows) > 1:
        header = rows[0]
        body = rows[1:]
    else:
        header = [f"col_{index + 1}" for index in range(len(rows[0]))]
        body = rows

    lines = []
    lines.append("| " + " | ".join(escape(value) for value in header) + " |")
    lines.append("| " + " | ".join("---" for _ in header) + " |")
    for row in body:
        lines.append("| " + " | ".join(escape(value) for value in row) + " |")
    return "\n".join(lines)


def save_debug_images(stages: dict[str, Any], output_dir: Path) -> None:
    debug_dir = output_dir / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    for name, image in stages.items():
        imwrite_unicode(debug_dir / f"{name}.png", image)


def show_stages(stages: dict[str, Any]) -> None:
    for name, image in stages.items():
        display = image
        if len(display.shape) == 2:
            display = cv2.cvtColor(display, cv2.COLOR_GRAY2BGR)
        display = resize_max_side(display, 1200)
        cv2.imshow(name, display)
        cv2.waitKey(0)
        cv2.destroyWindow(name)
    cv2.destroyAllWindows()


def main() -> int:
    args = parse_args()
    ensure_dependencies(require_paddle=not args.skip_ocr)

    image_path = Path(args.image)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    original = imread_unicode(image_path)
    processing_image = resize_max_side(original, args.max_side)

    stages: dict[str, Any] = {"00_original": processing_image.copy()}
    corrected, contour = perspective_correct(processing_image)
    stages["01_perspective_corrected"] = corrected.copy()

    preprocess_stages, binary = preprocess_for_ocr(corrected, args.line_mode)
    stages.update(preprocess_stages)

    horizontal, vertical, grid = detect_table_lines(
        binary, args.horizontal_scale, args.vertical_scale
    )
    stages["08_horizontal_lines"] = horizontal
    stages["09_vertical_lines"] = vertical
    stages["10_table_grid_mask"] = grid

    table_image, cropped_masks, _ = crop_to_table(
        corrected, horizontal, vertical, grid
    )
    stages["11_table_crop"] = table_image.copy()

    cropped_horizontal, cropped_vertical, cropped_grid = cropped_masks
    table_preprocess_stages, table_binary = preprocess_for_ocr(
        table_image, args.line_mode
    )
    table_horizontal, table_vertical, table_grid = detect_table_lines(
        table_binary, args.horizontal_scale, args.vertical_scale
    )

    # Prefer line masks recalculated on the crop. If they fail, keep the masks
    # cropped from the full image.
    if np.count_nonzero(table_grid) > np.count_nonzero(cropped_grid) * 0.25:
        cropped_horizontal = table_horizontal
        cropped_vertical = table_vertical
        cropped_grid = table_grid

    stages["12_table_binary"] = table_binary
    stages["13_table_horizontal_lines"] = cropped_horizontal
    stages["14_table_vertical_lines"] = cropped_vertical
    stages["15_table_grid_mask"] = cropped_grid

    cells, x_lines, y_lines = detect_cells(
        table_binary, cropped_horizontal, cropped_vertical, cropped_grid
    )
    detected_overlay = draw_cell_overlay(table_image, cells, include_text=False)
    stages["16_detected_cells"] = detected_overlay

    if args.skip_ocr:
        rows = [["" for _ in row] for row in cells]
    else:
        engine = PaddleOcrEngine(
            args.lang,
            args.use_gpu,
            args.min_score,
            args.paddle_engine,
            args.recognition_model,
        )
        rows = recognize_cells(table_image, cells, engine, args.cell_mode)
    if args.drop_empty_rows:
        rows = drop_empty_rows(rows)

    recognized_overlay = draw_cell_overlay(table_image, cells, include_text=True)
    stages["17_recognized_cells"] = recognized_overlay

    write_table_outputs(rows, output_dir)

    if not args.no_debug:
        save_debug_images(stages, output_dir)

    if args.show:
        show_stages(stages)

    print(markdown_table(rows, args.first_row_header))
    print()
    print(f"Saved outputs to: {output_dir.resolve()}")
    print(f"Detected rows: {len(rows)}")
    print(f"Detected x grid lines: {len(x_lines)}")
    print(f"Detected y grid lines: {len(y_lines)}")
    if contour is None:
        print("Perspective: document contour was not found; used source geometry.")
    else:
        print("Perspective: corrected from detected document contour.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
