from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.api.schemas import CellMode, EngineName, LineMode
from app.config import settings
from app.core.errors import NoCellsFoundError, OcrServiceError, TableNotFoundError
from app.core.logging import logger
from app.image_processing.cell_detection import Cell, detect_cells
from app.image_processing.debug import artifact, draw_cell_overlay
from app.image_processing.io import decode_image, resize_max_side, validate_image_upload
from app.image_processing.perspective import perspective_correct
from app.image_processing.preprocess import preprocess_cell, preprocess_for_ocr
from app.image_processing.table_detection import crop_to_table, detect_table_lines
from app.ocr_engines.fallback_engine import EngineSelection, engine_manager
from app.outputs.serializers import route_point_to_dict
from app.extraction.route_table_parser import extract_route_points, table_to_response


@dataclass(frozen=True)
class RouteTableOptions:
    engine: EngineName = "auto"
    lang: str = settings.default_lang
    cell_mode: CellMode = "auto"
    line_mode: LineMode = "aggressive"
    debug: bool = False
    extract_addresses: bool = True


@dataclass(frozen=True)
class PlainTextOptions:
    engine: EngineName = "auto"
    lang: str = settings.default_lang


def process_plain_text(filename: str | None, content: bytes, options: PlainTextOptions) -> dict[str, Any]:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    metadata = validate_image_upload(filename, content)
    image = decode_image(content)
    image, _ = resize_max_side(image, settings.max_image_side)

    selection = engine_manager.select(options.engine)
    try:
        lines = selection.engine.recognize_lines(image, lang=options.lang)
    except Exception as exc:
        if selection.engine.name == "paddle" and options.engine == "auto":
            selection = engine_manager.fallback_to_tesseract(exc)
            lines = selection.engine.recognize_lines(image, lang=options.lang)
        else:
            raise OcrServiceError("PROCESSING_FAILED", f"OCR recognition failed: {exc}", status_code=500) from exc

    payload = {
        "status": "ok",
        "engine": selection.engine.name,
        "mode": "plain_text",
        "raw_text": "\n".join(line.text for line in lines),
        "lines": [{"text": line.text, "confidence": line.confidence} for line in lines],
        "warnings": selection.warnings,
        "processing_time_ms": _elapsed_ms(started),
        "image_info": _image_info(metadata),
    }
    logger.info(
        "plain_text_ocr request_id=%s file=%s size=%s width=%s height=%s engine=%s lines=%s elapsed_ms=%s",
        request_id,
        filename,
        len(content),
        metadata.width,
        metadata.height,
        selection.engine.name,
        len(lines),
        payload["processing_time_ms"],
    )
    return payload


def process_route_table(filename: str | None, content: bytes, options: RouteTableOptions) -> dict[str, Any]:
    started = time.perf_counter()
    request_id = str(uuid.uuid4())
    metadata = validate_image_upload(filename, content)
    image = decode_image(content)
    image, _ = resize_max_side(image, settings.max_image_side)

    detection = detect_table_structure(image, line_mode=options.line_mode, include_debug=options.debug)
    cells = detection["cells"]
    if not cells:
        raise NoCellsFoundError()

    warnings: list[dict[str, str]] = []
    selection: EngineSelection | None = None
    if options.engine == "native_paddle":
        warnings.append(
            {
                "code": "NATIVE_PADDLE_EXPERIMENTAL",
                "message": "native_paddle is experimental; OpenCV table detection remains active",
            }
        )

    try:
        selection = engine_manager.select(options.engine)
        warnings.extend(selection.warnings)
        _recognize_cells(
            detection["table_image"],
            cells,
            selection,
            lang=options.lang,
            cell_mode=options.cell_mode,
        )
    except Exception as exc:
        if options.engine == "auto" and selection is not None and selection.engine.name == "paddle":
            selection = engine_manager.fallback_to_tesseract(exc)
            warnings.extend(selection.warnings)
            _clear_cell_text(cells)
            _recognize_cells(
                detection["table_image"],
                cells,
                selection,
                lang=options.lang,
                cell_mode=options.cell_mode,
            )
        else:
            raise OcrServiceError("PROCESSING_FAILED", f"OCR recognition failed: {exc}", status_code=500) from exc

    table = table_to_response(cells)
    route_points = [
        route_point_to_dict(point)
        for point in (extract_route_points(cells) if options.extract_addresses else [])
    ]
    if options.extract_addresses and not route_points:
        warnings.append(
            {
                "code": "NO_ROUTE_POINTS_EXTRACTED",
                "message": "No confident address rows were extracted from the detected table",
            }
        )

    debug_artifacts = detection["debug_artifacts"]
    if options.debug:
        debug_artifacts.append(artifact("17_recognized_cells", draw_cell_overlay(detection["table_image"], cells, include_text=True)))

    payload = {
        "status": "ok",
        "engine": selection.engine.name if selection else "none",
        "mode": "route_table",
        "processing_time_ms": _elapsed_ms(started),
        "image_info": _image_info(metadata),
        "raw_text": "\n".join(
            cell.text
            for row in cells
            for cell in row
            if cell.text
        ),
        "table": table,
        "route_points": route_points,
        "warnings": warnings,
        "debug": {
            "enabled": options.debug,
            "artifacts": debug_artifacts if options.debug and settings.enable_debug_artifacts else [],
            "request_id": request_id,
        },
    }
    logger.info(
        "route_table_ocr request_id=%s file=%s size=%s width=%s height=%s engine=%s rows=%s route_points=%s warnings=%s elapsed_ms=%s",
        request_id,
        filename,
        len(content),
        metadata.width,
        metadata.height,
        payload["engine"],
        table["rows_count"],
        len(route_points),
        [warning.get("code") for warning in warnings],
        payload["processing_time_ms"],
    )
    return payload


def process_debug_table(filename: str | None, content: bytes, line_mode: LineMode = "aggressive") -> dict[str, Any]:
    validate_image_upload(filename, content)
    image = decode_image(content)
    image, _ = resize_max_side(image, settings.max_image_side)
    detection = detect_table_structure(image, line_mode=line_mode, include_debug=True)
    cells = detection["cells"]
    columns_count = max((len(row) for row in cells), default=0)
    return {
        "status": "ok",
        "table_detected": bool(cells),
        "rows_count": len(cells),
        "columns_count": columns_count,
        "cells_count": sum(len(row) for row in cells),
        "debug_artifacts": detection["debug_artifacts"],
        "warnings": [] if cells else [{"code": "TABLE_NOT_FOUND", "message": "No table grid was detected"}],
    }


def detect_table_structure(image: Any, *, line_mode: str, include_debug: bool) -> dict[str, Any]:
    stages: dict[str, Any] = {"00_original": image.copy()}
    corrected, _ = perspective_correct(image)
    stages["01_perspective_corrected"] = corrected.copy()

    preprocess_stages, binary = preprocess_for_ocr(corrected, line_mode)
    stages.update(preprocess_stages)
    horizontal, vertical, grid = detect_table_lines(binary, settings.horizontal_scale, settings.vertical_scale)
    stages["08_horizontal_lines"] = horizontal
    stages["09_vertical_lines"] = vertical
    stages["10_table_grid_mask"] = grid

    if np.count_nonzero(grid) == 0:
        raise TableNotFoundError()

    table_image, cropped_masks, _ = crop_to_table(corrected, horizontal, vertical, grid)
    stages["11_table_crop"] = table_image.copy()
    cropped_horizontal, cropped_vertical, cropped_grid = cropped_masks

    _, table_binary = preprocess_for_ocr(table_image, line_mode)
    table_horizontal, table_vertical, table_grid = detect_table_lines(
        table_binary,
        settings.horizontal_scale,
        settings.vertical_scale,
    )
    if np.count_nonzero(table_grid) > np.count_nonzero(cropped_grid) * 0.25:
        cropped_horizontal = table_horizontal
        cropped_vertical = table_vertical
        cropped_grid = table_grid

    stages["12_table_binary"] = table_binary
    stages["13_table_horizontal_lines"] = cropped_horizontal
    stages["14_table_vertical_lines"] = cropped_vertical
    stages["15_table_grid_mask"] = cropped_grid

    cells, x_lines, y_lines = detect_cells(
        table_binary,
        cropped_horizontal,
        cropped_vertical,
        cropped_grid,
        min_cell_width=settings.min_cell_width,
        min_cell_height=settings.min_cell_height,
        merge_gap=settings.merge_gap,
    )
    if not cells:
        raise NoCellsFoundError()
    stages["16_detected_cells"] = draw_cell_overlay(table_image, cells, include_text=False)

    debug_artifacts = []
    if include_debug and settings.enable_debug_artifacts:
        for name in (
            "01_perspective_corrected",
            "10_table_grid_mask",
            "11_table_crop",
            "15_table_grid_mask",
            "16_detected_cells",
        ):
            if name in stages:
                debug_artifacts.append(artifact(name, stages[name]))

    return {
        "table_image": table_image,
        "cells": cells,
        "x_lines": x_lines,
        "y_lines": y_lines,
        "debug_artifacts": debug_artifacts,
    }


def _recognize_cells(
    table_image: Any,
    cells: list[list[Cell]],
    selection: EngineSelection,
    *,
    lang: str,
    cell_mode: str,
) -> None:
    as_bgr = selection.engine.name == "paddle"
    for row in cells:
        for cell in row:
            roi = _cell_roi(table_image, cell, raw_mode=cell_mode == "raw")
            if roi.size == 0:
                cell.text = ""
                cell.confidence = None
                continue
            prepared = preprocess_cell(roi, cell_mode, as_bgr=as_bgr)
            token = selection.engine.recognize_cell(prepared, lang=lang)
            cell.text = token.text
            cell.confidence = token.confidence


def _cell_roi(table_image: Any, cell: Cell, *, raw_mode: bool) -> Any:
    width = cell.x2 - cell.x1
    height = cell.y2 - cell.y1
    if raw_mode:
        pad_x = 1
        pad_y = 1
    else:
        pad_x = min(max(3, width // 18), 10)
        pad_y = min(max(3, height // 18), 10)
    x1 = min(max(cell.x1 + pad_x, 0), table_image.shape[1] - 1)
    y1 = min(max(cell.y1 + pad_y, 0), table_image.shape[0] - 1)
    x2 = max(min(cell.x2 - pad_x, table_image.shape[1]), x1 + 1)
    y2 = max(min(cell.y2 - pad_y, table_image.shape[0]), y1 + 1)
    return table_image[y1:y2, x1:x2]


def _clear_cell_text(cells: list[list[Cell]]) -> None:
    for row in cells:
        for cell in row:
            cell.text = ""
            cell.confidence = None


def _elapsed_ms(started: float) -> int:
    return int((time.perf_counter() - started) * 1000)


def _image_info(metadata: Any) -> dict[str, Any]:
    return {
        "width": metadata.width,
        "height": metadata.height,
        "format": metadata.format,
    }
