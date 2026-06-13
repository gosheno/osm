from __future__ import annotations

from app.extraction.address_extractor import extract_route_point


def test_extract_route_point_with_order_name_and_address() -> None:
    point = extract_route_point(
        0,
        ["1", "Пятерочка", "Санкт-Петербург, Невский проспект, 10"],
        [0.99, 0.95, 0.9],
    )

    assert point is not None
    assert point.original_order == 1
    assert point.name == "Пятерочка"
    assert point.address == "Санкт-Петербург, Невский проспект, 10"
    assert point.confidence >= 0.9


def test_header_row_is_ignored() -> None:
    point = extract_route_point(
        0,
        ["№", "Название", "Адрес"],
        [0.99, 0.99, 0.99],
    )

    assert point is None


def test_low_confidence_address_gets_warning() -> None:
    point = extract_route_point(
        0,
        ["Магазин", "СПб, Невский 10"],
        [0.8, 0.35],
    )

    assert point is not None
    assert any(warning["code"] == "LOW_CONFIDENCE_ADDRESS" for warning in point.warnings)

