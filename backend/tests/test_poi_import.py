from __future__ import annotations

from app.services.poi_import.address_normalizer import build_address, extract_address_fields
from app.services.poi_import.brand_normalizer import BrandAliasMatcher, normalize_brand_text
from app.services.poi_import.confidence import calculate_confidence
from app.services.poi_import.config import load_poi_config
from app.services.poi_import.duplicate_detector import mark_duplicates
from app.services.poi_import.models import PoiCandidate
from app.services.poi_import.tag_matcher import candidate_brand_match


def test_brand_normalization_handles_yo_and_apostrophes() -> None:
    assert normalize_brand_text("Пятёрочка") == normalize_brand_text("ПЯТЕРОЧКА")
    assert normalize_brand_text("О'КЕЙ") == normalize_brand_text("О’КЕЙ")


def test_tag_matcher_detects_configured_alias() -> None:
    config = load_poi_config()
    matcher = BrandAliasMatcher(config.chains)

    match = candidate_brand_match({"operator": "5-ka"}, matcher)

    assert match is not None
    assert match.canonical_brand == "Пятёрочка"


def test_address_building_prefers_city_street_house() -> None:
    tags = {
        "addr:city": "Санкт-Петербург",
        "addr:street": "Невский проспект",
        "addr:housenumber": "10",
        "addr:full": "weaker",
    }

    fields = extract_address_fields(tags, default_country="Russia")

    assert build_address(fields) == "Санкт-Петербург, Невский проспект, 10"


def test_duplicate_detector_marks_weaker_nearby_candidate() -> None:
    first = _candidate(
        osm_type="node",
        osm_id=1,
        street="Невский проспект",
        house_number="10",
        latitude=59.93,
        longitude=30.31,
    )
    second = _candidate(
        osm_type="way",
        osm_id=2,
        street=None,
        house_number=None,
        latitude=59.9301,
        longitude=30.3101,
    )

    mark_duplicates([first, second])

    assert first.is_duplicate is False
    assert second.is_duplicate is True
    assert second.duplicate_of_key == first.osm_key


def test_confidence_penalizes_missing_address() -> None:
    score = calculate_confidence(
        brand_matched=True,
        shop_type="supermarket",
        street=None,
        house_number=None,
        city=None,
        region=None,
        geometry_valid=True,
        warnings=["ADDRESS_MISSING"],
    )

    assert score < 0.8


def _candidate(
    *,
    osm_type: str,
    osm_id: int,
    street: str | None,
    house_number: str | None,
    latitude: float,
    longitude: float,
) -> PoiCandidate:
    address = f"Санкт-Петербург, {street}, {house_number}" if street and house_number else None
    return PoiCandidate(
        osm_type=osm_type,
        osm_id=osm_id,
        canonical_brand="ОКЕЙ",
        detected_brand="ОКЕЙ",
        name="ОКЕЙ",
        operator=None,
        shop_type="supermarket" if osm_type == "node" else None,
        amenity_type=None,
        original_address=address,
        normalized_address=address.lower() if address else None,
        city="Санкт-Петербург" if address else None,
        street=street,
        house_number=house_number,
        latitude=latitude,
        longitude=longitude,
        confidence_score=0.95 if address else 0.55,
    )

