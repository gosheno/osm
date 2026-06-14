from __future__ import annotations

import json
import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.nominatim_client import GeocodingCandidate, NominatimClient
from app.core.config import settings
from app.schemas.address import (
    AddressConfirmCandidate,
    AddressSuggestionItem,
)
from app.services.geocoding_context import WORK_AREA, is_within_work_area
from app.utils.address_normalizer import normalize_address


MIN_SUGGEST_QUERY_LENGTH = 3
MAX_SUGGEST_LIMIT = 10

CITY_MATCH_TOKENS = {
    "санкт",
    "петербург",
    "ленинградская",
    "область",
    "россия",
}

STREET_TYPE_TOKENS = {
    "ул",
    "улица",
    "улицы",
    "пр",
    "просп",
    "проспект",
    "пр-т",
    "пер",
    "переулок",
    "наб",
    "набережная",
    "пл",
    "площадь",
    "ш",
    "шоссе",
    "б-р",
    "бул",
    "бульвар",
    "проезд",
    "дорога",
}

STREET_TYPE_PATTERN = (
    r"улица|улицы|ул\.?|проспект|просп\.?|пр-т\.?|пр\.?|"
    r"переулок|пер\.?|набережная|наб\.?|площадь|пл\.?|"
    r"шоссе|ш\.?|бульвар|б-р\.?|бул\.?|проезд|дорога|линия"
)

STREET_TYPE_CANONICAL = {
    "ул": "улица",
    "улица": "улица",
    "улицы": "улица",
    "пр": "проспект",
    "просп": "проспект",
    "пр-т": "проспект",
    "проспект": "проспект",
    "пер": "переулок",
    "переулок": "переулок",
    "наб": "набережная",
    "набережная": "набережная",
    "пл": "площадь",
    "площадь": "площадь",
    "ш": "шоссе",
    "шоссе": "шоссе",
    "б-р": "бульвар",
    "бул": "бульвар",
    "бульвар": "бульвар",
}

HOUSE_NUMBER_PATTERN = (
    r"\d+(?!-?[яйе]\b)[0-9a-zа-я/-]*"
    r"(?:\s*(?:корпус|корп|к|строение|стр|литера|лит)\.?\s*[0-9a-zа-я/-]+)*"
)


class AddressSuggestQueryTooShortError(ValueError):
    pass


def clamp_limit(limit: int | None) -> int:
    if limit is None:
        limit = settings.NOMINATIM_DEFAULT_LIMIT
    return max(1, min(int(limit), MAX_SUGGEST_LIMIT))


def split_display_name(display_name: str) -> tuple[str, str | None]:
    parts = [part.strip() for part in display_name.split(",") if part.strip()]
    if not parts:
        return display_name, None
    if len(parts) == 1:
        return parts[0], None
    return ", ".join(parts[:2]), ", ".join(parts[2:])


def address_secondary_text(address: dict[str, Any], display_name: str) -> str | None:
    values = [
        address.get("shop"),
        address.get("amenity"),
        address.get("tourism"),
        address.get("building"),
        address.get("allotments"),
        address.get("neighbourhood"),
        address.get("quarter"),
        address.get("suburb"),
        address.get("city_district"),
        address.get("municipality"),
        address.get("hamlet"),
        address.get("village"),
        address.get("town"),
        address.get("city"),
        address.get("county"),
        address.get("state_district"),
        address.get("state") or address.get("region"),
        address.get("postcode"),
        address.get("country"),
    ]
    cleaned: list[str] = []
    for value in values:
        if value and value not in cleaned:
            cleaned.append(str(value))

    if cleaned:
        return ", ".join(cleaned)

    _main, secondary = split_display_name(display_name)
    return secondary


def address_main_text(address: dict[str, Any], display_name: str) -> str:
    road = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
        or address.get("path")
        or address.get("neighbourhood")
    )
    house = address.get("house_number")
    name = address.get("building") or address.get("amenity") or address.get("shop")

    if road and house:
        return f"{road}, {house}"
    if road:
        return str(road)
    if name and house:
        return f"{name}, {house}"
    if name:
        return str(name)

    main, _secondary = split_display_name(display_name)
    return main


def confidence_from_candidate(candidate: GeocodingCandidate) -> float:
    raw = candidate.raw or {}
    address = raw.get("address") if isinstance(raw.get("address"), dict) else {}

    score = 45.0
    if candidate.importance is not None:
        score += min(float(candidate.importance) * 45.0, 35.0)

    place_rank = candidate.place_rank
    if place_rank is not None:
        if place_rank >= 30:
            score += 15.0
        elif place_rank <= 26:
            score -= 15.0

    if address.get("house_number"):
        score += 15.0
    if not is_within_work_area(candidate.latitude, candidate.longitude):
        score -= 40.0

    return round(max(0.0, min(score, 99.0)), 2)


def suggestion_id(
    *,
    provider: str,
    osm_type: str | None,
    osm_id: int | None,
    place_id: int | None,
    address_id: int | None = None,
) -> str:
    if address_id is not None:
        return f"address:{address_id}"
    if osm_type and osm_id is not None:
        return f"{provider}:{osm_type}:{osm_id}"
    if place_id is not None:
        return f"{provider}:place:{place_id}"
    return f"{provider}:candidate"


def safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def query_has_house_number(query: str) -> bool:
    value = query.lower().replace("ё", "е").strip()
    if re.search(r"(^|[\s,])(дом|д)\.?\s*\d", value):
        return True
    return bool(re.search(rf"(^|[\s,]){HOUSE_NUMBER_PATTERN}$", value))


def item_is_street_completion(item: AddressSuggestionItem) -> bool:
    address = item.address or {}
    if address.get("house_number"):
        return False
    if (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
        or address.get("path")
    ):
        return True

    category = (item.category or "").lower()
    item_type = (item.type or "").lower()
    return category == "highway" or item_type in {
        "road",
        "residential",
        "primary",
        "secondary",
        "tertiary",
        "unclassified",
        "service",
        "living_street",
        "pedestrian",
    }


def street_text_from_item(item: AddressSuggestionItem) -> str:
    address = item.address or {}
    explicit_street = (
        address.get("road")
        or address.get("pedestrian")
        or address.get("footway")
        or address.get("path")
    )
    if explicit_street:
        return str(explicit_street)

    raw_address = address.get("address")
    if isinstance(raw_address, str):
        parsed = extract_street_text(raw_address)
        if parsed:
            return parsed

    for value in (item.main_text, item.display_name):
        parsed = extract_street_text(value or "")
        if parsed:
            return parsed
    return str(item.main_text or "")


def street_completion_matches_query(item: AddressSuggestionItem, query: str) -> bool:
    street_tokens = match_tokens(street_text_from_item(item))
    query_tokens = match_tokens(query)
    if not street_tokens or not query_tokens:
        return False
    return any(
        street_token == query_token
        or street_token.startswith(query_token)
        or query_token.startswith(street_token)
        for street_token in street_tokens
        for query_token in query_tokens
    )


def match_tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[0-9a-zA-Zа-яА-Я]+", value.lower().replace("ё", "е"))
        if (token.isdigit() or len(token) >= 3)
        and token not in CITY_MATCH_TOKENS
        and token not in STREET_TYPE_TOKENS
    }


def extract_street_text(value: str) -> str | None:
    value = normalize_street_source(value)
    if not value:
        return None

    parts = [part.strip() for part in value.split(",") if part.strip()]
    for part in parts:
        if street_part_has_type(part):
            return format_street_text(part)

    stripped = strip_house_suffix(strip_city_prefix(value))
    if stripped != value and has_alpha_token(stripped):
        return format_street_text(stripped)
    return None


def normalize_street_source(value: str) -> str:
    value = (value or "").strip()
    value = value.replace("ё", "е")
    value = value.replace(";", ",").replace("|", ",").replace("\t", " ")
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    return value.strip(" ,")


def strip_city_prefix(value: str) -> str:
    prefixes = (
        "санкт-петербург",
        "санкт петербург",
        "спб",
        "петербург",
        "ленинградская область",
        "россия",
    )
    stripped = value.strip(" ,")
    for prefix in prefixes:
        stripped = re.sub(
            rf"^{re.escape(prefix)}\s*,?\s*",
            "",
            stripped,
            flags=re.IGNORECASE,
        )
    return stripped.strip(" ,")


def strip_house_suffix(value: str) -> str:
    value = value.strip(" ,")
    value = re.sub(
        rf"\b(?:дом|д)\.?\s*{HOUSE_NUMBER_PATTERN}\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        rf",\s*{HOUSE_NUMBER_PATTERN}\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    value = re.sub(
        rf"\s+{HOUSE_NUMBER_PATTERN}\s*$",
        "",
        value,
        flags=re.IGNORECASE,
    )
    return value.strip(" ,")


def looks_like_house_part(value: str | None) -> bool:
    if not value:
        return False
    value = value.lower().replace("ё", "е").strip(" ,")
    return bool(
        re.fullmatch(
            rf"(?:дом|д)?\.?\s*{HOUSE_NUMBER_PATTERN}",
            value,
            flags=re.IGNORECASE,
        )
    )


def street_part_has_type(value: str) -> bool:
    return bool(
        re.search(
            rf"(^|\s)({STREET_TYPE_PATTERN})($|\s)",
            value,
            flags=re.IGNORECASE,
        )
    )


def has_alpha_token(value: str) -> bool:
    return bool(re.search(r"[a-zA-Zа-яА-Я]{3,}", value))


def format_street_text(value: str) -> str:
    value = strip_house_suffix(strip_city_prefix(normalize_street_source(value)))
    value = re.sub(r"\s+", " ", value).strip(" ,")

    prefix = re.match(
        rf"^({STREET_TYPE_PATTERN})\s+(.+)$",
        value,
        flags=re.IGNORECASE,
    )
    if prefix:
        street_type = canonical_street_type(prefix.group(1))
        street_name = prefix.group(2).strip(" ,")
        return f"{street_type} {street_name}" if street_type else value

    suffix = re.match(r"^(.+?)\s+(ул\.?|улица|улицы)$", value, flags=re.IGNORECASE)
    if suffix:
        street_name = suffix.group(1).strip(" ,")
        return f"улица {street_name}"

    return value


def canonical_street_type(value: str) -> str | None:
    key = value.lower().replace(".", "").strip()
    return STREET_TYPE_CANONICAL.get(key, key or None)


def street_secondary_text(item: AddressSuggestionItem, street: str) -> str | None:
    display_parts = [
        part.strip()
        for part in (item.display_name or "").split(",")
        if part.strip()
    ]
    street_key = " ".join(sorted(match_tokens(street)))
    useful_parts: list[str] = []
    for part in display_parts:
        part_lower = part.lower().replace("ё", "е")
        if part_lower in {"санкт-петербург", "санкт петербург", "спб"}:
            useful_parts.append(part)
            continue
        if looks_like_house_part(part):
            continue

        part_tokens = " ".join(sorted(match_tokens(part)))
        if not part_tokens or part_tokens == street_key:
            continue
        if part_lower in CITY_MATCH_TOKENS:
            continue
        useful_parts.append(part)

    if useful_parts:
        return ", ".join(useful_parts[:3])

    if item.secondary_text and not looks_like_house_part(item.secondary_text):
        return item.secondary_text
    return None


def street_completion_items_from_items(
    items: list[AddressSuggestionItem],
    *,
    query: str,
) -> list[AddressSuggestionItem]:
    best_by_street: dict[str, AddressSuggestionItem] = {}

    for item in items:
        if item.geocoding_status not in {"found", "manual"}:
            continue

        street = street_text_from_item(item)
        if not street:
            continue

        address = dict(item.address or {})
        address.pop("house_number", None)
        address.pop("house", None)
        address["road"] = street

        street_item = AddressSuggestionItem(
            id=f"street:{normalize_street_source(street).lower()}",
            provider=item.provider,
            display_name=street,
            main_text=street,
            secondary_text=street_secondary_text(item, street),
            latitude=item.latitude,
            longitude=item.longitude,
            osm_type=item.osm_type,
            osm_id=item.osm_id,
            place_id=item.place_id,
            category="highway",
            type="road",
            importance=item.importance,
            confidence_score=item.confidence_score,
            address=address,
            geocoding_status="found",
            source=item.source,
            outside_supported_region=item.outside_supported_region,
        )

        if not street_completion_matches_query(street_item, query):
            continue

        key = " ".join(sorted(match_tokens(street)))
        if not key:
            continue
        current = best_by_street.get(key)
        if current is None or (street_item.confidence_score or 0) > (
            current.confidence_score or 0
        ):
            best_by_street[key] = street_item

    return list(best_by_street.values())


def sort_suggestion_items(
    items: list[AddressSuggestionItem],
    *,
    query: str,
) -> list[AddressSuggestionItem]:
    prefer_streets = not query_has_house_number(query)
    return sorted(
        items,
        key=lambda item: (
            0
            if (
                prefer_streets
                and item_is_street_completion(item)
                and street_completion_matches_query(item, query)
            )
            else 1,
            item.source != "database",
            -(item.confidence_score or 0),
        ),
    )


def item_from_candidate(candidate: GeocodingCandidate) -> AddressSuggestionItem:
    raw = candidate.raw or {}
    address = raw.get("address") if isinstance(raw.get("address"), dict) else {}
    display_name = candidate.display_name or ""
    osm_type = raw.get("osm_type")
    osm_id = safe_int(raw.get("osm_id"))
    place_id = safe_int(raw.get("place_id"))

    return AddressSuggestionItem(
        id=suggestion_id(
            provider="nominatim",
            osm_type=osm_type,
            osm_id=osm_id,
            place_id=place_id,
        ),
        provider="nominatim",
        display_name=display_name,
        main_text=address_main_text(address, display_name),
        secondary_text=address_secondary_text(address, display_name),
        latitude=candidate.latitude,
        longitude=candidate.longitude,
        osm_type=osm_type,
        osm_id=osm_id,
        place_id=place_id,
        category=raw.get("class"),
        type=raw.get("type"),
        importance=candidate.importance,
        confidence_score=confidence_from_candidate(candidate),
        address=address,
        geocoding_status="found",
        source="nominatim",
        outside_supported_region=not is_within_work_area(
            candidate.latitude,
            candidate.longitude,
        ),
    )


def item_from_cache(row: dict[str, Any]) -> AddressSuggestionItem:
    display_name = row.get("display_name") or row.get("original_address") or ""
    address = row.get("raw_response")
    if isinstance(address, str):
        try:
            address = json.loads(address)
        except json.JSONDecodeError:
            address = {}
    if isinstance(address, dict) and isinstance(address.get("address"), dict):
        address = address["address"]
    if not isinstance(address, dict):
        address = {}

    latitude = float(row["latitude"])
    longitude = float(row["longitude"])
    return AddressSuggestionItem(
        id=suggestion_id(
            provider=row.get("geocoding_provider") or "nominatim",
            osm_type=row.get("osm_type"),
            osm_id=row.get("osm_id"),
            place_id=row.get("place_id"),
            address_id=row.get("id"),
        ),
        provider=row.get("geocoding_provider") or "nominatim",
        display_name=display_name,
        main_text=address_main_text(address, display_name),
        secondary_text=address_secondary_text(address, display_name),
        latitude=latitude,
        longitude=longitude,
        osm_type=row.get("osm_type"),
        osm_id=row.get("osm_id"),
        place_id=row.get("place_id"),
        confidence_score=(
            float(row["geocoding_score"])
            if row.get("geocoding_score") is not None
            else
            float(row["confidence_score"])
            if row.get("confidence_score") is not None
            else None
        ),
        address=address,
        geocoding_status=row.get("geocoding_status") or "found",
        source="database",
        outside_supported_region=not is_within_work_area(latitude, longitude),
    )


class AddressSuggestionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def suggest(
        self,
        *,
        query: str,
        limit: int | None = None,
        lang: str | None = None,
        bounded: bool | None = None,
        viewbox: str | None = None,
        context_city: str | None = None,
        context_region: str | None = None,
    ) -> tuple[str, list[AddressSuggestionItem]]:
        clean_query = query.strip()
        if len(clean_query) < MIN_SUGGEST_QUERY_LENGTH:
            raise AddressSuggestQueryTooShortError(
                "Enter at least 3 characters to search for an address."
            )

        default_city = context_city or settings.DEFAULT_CITY
        normalized = normalize_address(clean_query, default_city=default_city)
        normalized_query = normalized.normalized_address
        result_limit = clamp_limit(limit)
        prefer_streets = not query_has_house_number(clean_query)

        cached = await self._cached_suggestions(
            normalized_query=normalized_query,
            query=clean_query,
            limit=result_limit * 3 if prefer_streets else result_limit,
        )

        if prefer_streets:
            items = deduplicate_items(
                street_completion_items_from_items(cached, query=clean_query) + cached
            )
        else:
            items = deduplicate_items(cached)[:result_limit]

        remaining = result_limit - len(items)
        if remaining <= 0 and not prefer_streets:
            return normalized_query, sort_suggestion_items(items, query=clean_query)

        search_query = normalized_query
        if context_region and context_region.lower() not in search_query.lower():
            search_query = f"{search_query}, {context_region}"

        candidates = await NominatimClient().search(
            search_query,
            limit=result_limit if prefer_streets else remaining,
            language=lang,
            viewbox=viewbox,
            bounded=bounded,
        )
        seen = {dedupe_key(item) for item in items}
        for candidate in candidates:
            item = item_from_candidate(candidate)
            key = dedupe_key(item)
            if key in seen:
                continue
            seen.add(key)
            items.append(item)

        items = sort_suggestion_items(deduplicate_items(items), query=clean_query)
        return normalized_query, items[:result_limit]

    async def _cached_suggestions(
        self,
        *,
        normalized_query: str,
        query: str,
        limit: int,
    ) -> list[AddressSuggestionItem]:
        result = await self.db.execute(
            text(
                """
                SELECT
                    id,
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geocoding_status,
                    geocoding_provider,
                    confidence_score,
                    geocoding_score,
                    display_name,
                    osm_type,
                    osm_id,
                    place_id,
                    raw_response
                FROM addresses
                WHERE latitude IS NOT NULL
                  AND longitude IS NOT NULL
                  AND geocoding_status IN ('found', 'ambiguous', 'manual')
                  AND (
                    normalized_address = :normalized_query
                    OR normalized_address ILIKE :normalized_like
                    OR original_address ILIKE :query_like
                    OR display_name ILIKE :query_like
                  )
                ORDER BY
                  CASE WHEN normalized_address = :normalized_query THEN 0 ELSE 1 END,
                  last_used_at DESC NULLS LAST,
                  updated_at DESC
                LIMIT :limit
                """
            ),
            {
                "normalized_query": normalized_query,
                "normalized_like": f"%{normalized_query}%",
                "query_like": f"%{query}%",
                "limit": limit,
            },
        )
        return [item_from_cache(dict(row)) for row in result.mappings().all()]

    async def confirm(
        self,
        *,
        original_query: str,
        selected_candidate: AddressConfirmCandidate,
    ) -> dict[str, Any]:
        normalized = normalize_address(
            selected_candidate.display_name or original_query,
            default_city=None,
        )
        raw_payload = selected_candidate.raw or {
            "address": selected_candidate.address,
            "display_name": selected_candidate.display_name,
            "lat": selected_candidate.latitude,
            "lon": selected_candidate.longitude,
            "osm_type": selected_candidate.osm_type,
            "osm_id": selected_candidate.osm_id,
            "place_id": selected_candidate.place_id,
        }
        raw_json = json.dumps(raw_payload, ensure_ascii=False)

        result = await self.db.execute(
            text(
                """
                INSERT INTO addresses (
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geom,
                    geocoding_status,
                    geocoding_provider,
                    confidence_score,
                    display_name,
                    osm_type,
                    osm_id,
                    place_id,
                    raw_response,
                    last_used_at
                )
                VALUES (
                    :original_address,
                    :normalized_address,
                    :latitude,
                    :longitude,
                    ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326),
                    :geocoding_status,
                    :geocoding_provider,
                    :confidence_score,
                    :display_name,
                    :osm_type,
                    :osm_id,
                    :place_id,
                    CAST(:raw_response AS jsonb),
                    now()
                )
                ON CONFLICT (normalized_address)
                DO UPDATE SET
                    original_address = EXCLUDED.original_address,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    geom = EXCLUDED.geom,
                    geocoding_status = EXCLUDED.geocoding_status,
                    geocoding_provider = EXCLUDED.geocoding_provider,
                    confidence_score = EXCLUDED.confidence_score,
                    display_name = EXCLUDED.display_name,
                    osm_type = EXCLUDED.osm_type,
                    osm_id = EXCLUDED.osm_id,
                    place_id = EXCLUDED.place_id,
                    raw_response = EXCLUDED.raw_response,
                    last_used_at = now()
                RETURNING
                    id,
                    latitude,
                    longitude,
                    geocoding_status
                """
            ),
            {
                "original_address": original_query.strip(),
                "normalized_address": normalized.normalized_address,
                "latitude": selected_candidate.latitude,
                "longitude": selected_candidate.longitude,
                "geocoding_status": selected_candidate.geocoding_status or "found",
                "geocoding_provider": selected_candidate.provider,
                "confidence_score": selected_candidate.confidence_score,
                "display_name": selected_candidate.display_name,
                "osm_type": selected_candidate.osm_type,
                "osm_id": selected_candidate.osm_id,
                "place_id": selected_candidate.place_id,
                "raw_response": raw_json,
            },
        )
        await self.db.commit()
        return dict(result.mappings().one())


def supported_area_bounds() -> dict[str, float]:
    return dict(WORK_AREA)


def dedupe_key(item: AddressSuggestionItem) -> tuple:
    return (
        round(item.latitude, 6),
        round(item.longitude, 6),
        item.display_name.lower().strip(),
    )


def deduplicate_items(items: list[AddressSuggestionItem]) -> list[AddressSuggestionItem]:
    seen: set[tuple] = set()
    deduped: list[AddressSuggestionItem] = []
    for item in items:
        key = dedupe_key(item)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped
