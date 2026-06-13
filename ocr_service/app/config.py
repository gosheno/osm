from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _int_env(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or value == "":
        return default
    return value.lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    service_version: str = "0.2.0"
    default_engine: str = os.getenv("OCR_DEFAULT_ENGINE", "auto")
    default_lang: str = os.getenv("OCR_DEFAULT_LANG", "ru")
    fallback_lang: str = os.getenv("OCR_FALLBACK_LANG", "cyrillic")
    max_file_size_mb: int = _int_env("OCR_MAX_FILE_SIZE_MB", 10)
    max_image_side: int = _int_env("OCR_MAX_IMAGE_SIDE", 4000)
    debug_artifact_ttl_minutes: int = _int_env("OCR_DEBUG_ARTIFACT_TTL_MINUTES", 60)
    enable_debug_artifacts: bool = _bool_env("OCR_ENABLE_DEBUG_ARTIFACTS", True)
    debug_artifact_dir: Path = Path(os.getenv("OCR_DEBUG_ARTIFACT_DIR", "/tmp/ocr-debug"))
    horizontal_scale: int = _int_env("OCR_HORIZONTAL_SCALE", 35)
    vertical_scale: int = _int_env("OCR_VERTICAL_SCALE", 35)
    min_cell_width: int = _int_env("OCR_MIN_CELL_WIDTH", 8)
    min_cell_height: int = _int_env("OCR_MIN_CELL_HEIGHT", 8)
    merge_gap: int = _int_env("OCR_MERGE_GAP", 4)

    @property
    def max_file_size_bytes(self) -> int:
        return self.max_file_size_mb * 1024 * 1024


os.environ.setdefault("PADDLE_PDX_ENABLE_MKLDNN_BYDEFAULT", "0")
os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")

settings = Settings()

