from __future__ import annotations

from app.utils.address_normalizer import normalize_address


ADDRESS_KEYS = {
    "country": "addr:country",
    "region": "addr:region",
    "city": "addr:city",
    "district": "addr:district",
    "suburb": "addr:suburb",
    "street": "addr:street",
    "house_number": "addr:housenumber",
    "postcode": "addr:postcode",
    "place": "addr:place",
    "full": "addr:full",
}


def extract_address_fields(tags: dict[str, str], *, default_country: str) -> dict[str, str | None]:
    return {
        "country": tags.get(ADDRESS_KEYS["country"]) or default_country,
        "region": tags.get(ADDRESS_KEYS["region"]) or tags.get("is_in:state"),
        "city": tags.get(ADDRESS_KEYS["city"]),
        "district": tags.get(ADDRESS_KEYS["district"]),
        "suburb": tags.get(ADDRESS_KEYS["suburb"]),
        "street": tags.get(ADDRESS_KEYS["street"]),
        "house_number": tags.get(ADDRESS_KEYS["house_number"]),
        "postcode": tags.get(ADDRESS_KEYS["postcode"]),
        "place": tags.get(ADDRESS_KEYS["place"]),
        "full": tags.get(ADDRESS_KEYS["full"]),
    }


def build_address(fields: dict[str, str | None]) -> str | None:
    city = _clean(fields.get("city"))
    street = _clean(fields.get("street"))
    house = _clean(fields.get("house_number"))
    place = _clean(fields.get("place"))
    full = _clean(fields.get("full"))

    if city and street and house:
        return f"{city}, {street}, {house}"
    if street and house:
        return f"{street}, {house}"
    if place and house:
        return f"{place}, {house}"
    return full


def normalized_known_poi_address(address: str | None, *, default_city: str | None) -> str | None:
    if not address:
        return None
    try:
        return normalize_address(address, default_city=default_city).normalized_address
    except ValueError:
        return " ".join(address.lower().split())


def address_completeness(fields: dict[str, str | None]) -> int:
    score = 0
    for key in ("city", "region", "district", "suburb", "street", "house_number", "postcode", "place", "full"):
        if fields.get(key):
            score += 1
    return score


def _clean(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None

