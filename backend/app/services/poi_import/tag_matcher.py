from __future__ import annotations

from app.services.poi_import.brand_normalizer import BrandAliasMatcher, BrandMatch


PRIMARY_BRAND_TAGS = (
    "brand",
    "brand:ru",
    "operator",
    "operator:ru",
)

SECONDARY_BRAND_TAGS = (
    "name",
    "name:ru",
    "name:en",
    "official_name",
    "short_name",
    "alt_name",
    "old_name",
)

WEAK_BRAND_TAGS = (
    "description",
)


def candidate_brand_match(tags: dict[str, str], matcher: BrandAliasMatcher) -> BrandMatch | None:
    for tag_name in PRIMARY_BRAND_TAGS:
        match = _match_tag(tags, tag_name, matcher)
        if match is not None:
            return match

    for tag_name in SECONDARY_BRAND_TAGS:
        match = _match_tag(tags, tag_name, matcher)
        if match is not None:
            return match

    for tag_name in WEAK_BRAND_TAGS:
        match = _match_tag(tags, tag_name, matcher)
        if match is not None:
            return match

    return None


def _match_tag(
    tags: dict[str, str],
    tag_name: str,
    matcher: BrandAliasMatcher,
) -> BrandMatch | None:
    value = tags.get(tag_name)
    if not value:
        return None

    return matcher.detect(value)