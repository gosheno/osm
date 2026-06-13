from __future__ import annotations

import pytest


def test_health_endpoint_shape() -> None:
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from app.main import app

    response = TestClient(app).get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "ocr"
    assert payload["version"] == "0.2.0"
    assert "paddle" in payload["engines"]
    assert "tesseract" in payload["engines"]

