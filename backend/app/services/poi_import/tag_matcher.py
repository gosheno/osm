from __future__ import annotations

from app.services.poi_import.brand_normalizer import BrandAliasMatcher, BrandMatch


BRAND_TAGS = (
    "name",
    "name:ru",
    "brand",
    "brand:ru",
    "operator",
    "operator:ru",
    "official_name",
    "short_name",
)


def candidate_brand_match(tags: dict[str, str], matcher: BrandAliasMatcher) -> BrandMatch | None:
    for tag_name in BRAND_TAGS:
        match = matcher.detect(tags.get(tag_name))
        if match is not None:
            return match
    return None

