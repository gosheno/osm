from __future__ import annotations

import pytest

from app.core.errors import InvalidImageError
from app.image_processing.io import validate_image_upload


def test_invalid_image_upload_is_rejected() -> None:
    with pytest.raises(InvalidImageError):
        validate_image_upload("not-image.txt", b"hello")

