from __future__ import annotations

import shutil
from pathlib import Path


SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".webp"}


class ImagePreprocessingError(Exception):
    pass


def preprocess_image(source_path: Path, target_path: Path) -> Path:
    """Create an OCR-friendly copy while keeping preprocessing independent."""
    target_path.parent.mkdir(parents=True, exist_ok=True)

    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps
    except Exception:
        shutil.copy2(source_path, target_path)
        return target_path

    try:
        with Image.open(source_path) as image:
            image = ImageOps.exif_transpose(image)
            image = image.convert("L")

            max_side = max(image.size)
            if max_side < 1800:
                scale = 1800 / max_side
                image = image.resize(
                    (int(image.width * scale), int(image.height * scale)),
                    Image.Resampling.LANCZOS,
                )

            image = ImageEnhance.Contrast(image).enhance(1.45)
            image = ImageEnhance.Sharpness(image).enhance(1.25)
            image = image.filter(ImageFilter.MedianFilter(size=3))
            image.save(target_path)
    except Exception as exc:
        raise ImagePreprocessingError(str(exc)) from exc

    return target_path
