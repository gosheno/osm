from __future__ import annotations


GOOD_SHOP_TAGS = {"supermarket", "convenience", "department_store", "greengrocer", "yes"}


def calculate_confidence(
    *,
    brand_matched: bool,
    shop_type: str | None,
    street: str | None,
    house_number: str | None,
    city: str | None,
    region: str | None,
    geometry_valid: bool,
    warnings: list[str],
) -> float:
    score = 0.0
    if brand_matched:
        score += 0.4
    if shop_type in GOOD_SHOP_TAGS:
        score += 0.2
    if street and house_number:
        score += 0.2
    if city or region:
        score += 0.1
    if geometry_valid:
        score += 0.1

    penalties = {
        "ADDRESS_MISSING": 0.2,
        "SHOP_TAG_MISSING": 0.2,
        "DUPLICATE_CANDIDATE": 0.2,
        "GEOMETRY_UNCERTAIN": 0.3,
    }
    for warning in warnings:
        score -= penalties.get(warning, 0.0)
    return round(max(0.0, min(score, 1.0)), 4)

