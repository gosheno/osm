from __future__ import annotations

import math
from difflib import SequenceMatcher

from app.services.poi_import.address_normalizer import address_completeness
from app.services.poi_import.models import PoiCandidate


SAME_PLACE_THRESHOLD_M = 30.0
POSSIBLE_DUPLICATE_THRESHOLD_M = 80.0


def mark_duplicates(candidates: list[PoiCandidate]) -> list[PoiCandidate]:
    by_brand: dict[str, list[PoiCandidate]] = {}
    for candidate in candidates:
        by_brand.setdefault(candidate.canonical_brand, []).append(candidate)

    for brand_candidates in by_brand.values():
        for index, current in enumerate(brand_candidates):
            if current.is_duplicate:
                continue
            nearby = [
                other
                for other in brand_candidates[index + 1 :]
                if _looks_duplicate(current, other)
            ]
            if not nearby:
                continue
            group = [current, *nearby]
            keeper = max(group, key=_candidate_quality)
            for item in group:
                if item is keeper:
                    continue
                item.is_duplicate = True
                item.duplicate_of_key = keeper.osm_key
                if "DUPLICATE_CANDIDATE" not in item.warnings:
                    item.warnings.append("DUPLICATE_CANDIDATE")
                item.confidence_score = round(max(0.0, item.confidence_score - 0.2), 4)
    return candidates


def haversine_meters(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    radius = 6371000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2) ** 2
    )
    return radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def _looks_duplicate(left: PoiCandidate, right: PoiCandidate) -> bool:
    distance = haversine_meters(left.latitude, left.longitude, right.latitude, right.longitude)
    if distance <= SAME_PLACE_THRESHOLD_M:
        return True
    if distance > POSSIBLE_DUPLICATE_THRESHOLD_M:
        return False
    if not left.normalized_address or not right.normalized_address:
        return False
    return SequenceMatcher(None, left.normalized_address, right.normalized_address).ratio() >= 0.86


def _candidate_quality(candidate: PoiCandidate) -> tuple[int, int, float]:
    fields = {
        "city": candidate.city,
        "region": candidate.region,
        "district": candidate.district,
        "suburb": candidate.suburb,
        "street": candidate.street,
        "house_number": candidate.house_number,
        "postcode": candidate.postcode,
        "full": candidate.original_address,
    }
    osm_type_score = 2 if candidate.osm_type == "node" and candidate.shop_type else 1
    return (address_completeness(fields), osm_type_score, candidate.confidence_score)
