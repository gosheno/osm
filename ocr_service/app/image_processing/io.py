from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from PIL import Image, ImageOps, UnidentifiedImageError

from app.config import settings
from app.core.errors import FileTooLargeError, InvalidImageError


SUPPORTED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
SUPPORTED_FORMATS = {"jpeg", "png", "webp"}


@dataclass(frozen=True)
class ImageMetadata:
    width: int
    height: int
    format: str | None


def validate_image_upload(filename: str | None, content: bytes) -> ImageMetadata:
    if len(content) > settings.max_file_size_bytes:
        raise FileTooLargeError(settings.max_file_size_mb)

    suffix = Path(filename or "").suffix.lower()
    if suffix and suffix not in SUPPORTED_EXTENSIONS:
        raise InvalidImageError()

    try:
        with Image.open(BytesIO(content)) as image:
            image_format = (image.format or "").lower()
            image = ImageOps.exif_transpose(image)
            if image_format not in SUPPORTED_FORMATS:
                raise InvalidImageError()
            width, height = image.size
    except (UnidentifiedImageError, OSError):
        raise InvalidImageError()

    if width <= 0 or height <= 0:
        raise InvalidImageError()
    return ImageMetadata(width=width, height=height, format=image_format)


def decode_image(content: bytes) -> Any:
    data = np.frombuffer(content, dtype=np.uint8)
    image = cv2.imdecode(data, cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidImageError()
    return image


def resize_max_side(image: Any, max_side: int) -> tuple[Any, float]:
    if max_side <= 0:
        return image, 1.0
    height, width = image.shape[:2]
    scale = max_side / float(max(height, width))
    if scale >= 1.0:
        return image, 1.0
    new_size = (max(1, int(width * scale)), max(1, int(height * scale)))
    return cv2.resize(image, new_size, interpolation=cv2.INTER_AREA), scale
