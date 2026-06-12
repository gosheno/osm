from __future__ import annotations

import json
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
        address.get("city")
        or address.get("town")
        or address.get("village")
        or address.get("municipality")
        or address.get("suburb"),
        address.get("state") or address.get("region"),
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

        cached = await self._cached_suggestions(
            normalized_query=normalized_query,
            query=clean_query,
            limit=result_limit,
        )

        items = deduplicate_items(cached)[:result_limit]
        remaining = result_limit - len(items)
        if remaining <= 0:
            return normalized_query, items

        search_query = normalized_query
        if context_region and context_region.lower() not in search_query.lower():
            search_query = f"{search_query}, {context_region}"

        candidates = await NominatimClient().search(
            search_query,
            limit=remaining,
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

        items.sort(
            key=lambda item: (
                item.source != "database",
                -(item.confidence_score or 0),
            )
        )
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
