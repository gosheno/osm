from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.nominatim_client import NominatimClient
from app.repositories.address_repository import (
    get_address_by_normalized,
    touch_address_last_used,
    upsert_address,
)
from app.schemas.address import AddressGeocodeResponse
from app.utils.address_normalizer import normalize_address


def estimate_confidence_score(
    *,
    query: str,
    display_name: str,
    importance: float | None,
) -> float:
    score = 50.0

    query_lower = query.lower()
    display_lower = display_name.lower()

    for token in query_lower.replace(",", " ").split():
        if token and token in display_lower:
            score += 5.0

    if importance is not None:
        score += min(importance * 30.0, 20.0)

    return min(score, 99.0)


async def geocode_address(
    db: AsyncSession,
    *,
    address: str,
    default_city: str | None = "санкт-петербург",
    force_refresh: bool = False,
) -> AddressGeocodeResponse:
    normalized = normalize_address(address, default_city=default_city)

    cached = await get_address_by_normalized(
        db,
        normalized.normalized_address,
    )

    if (
        cached
        and not force_refresh
        and cached["latitude"] is not None
        and cached["longitude"] is not None
        and cached["geocoding_status"] in {"found", "manual"}
    ):
        await touch_address_last_used(db, cached["id"])

        return AddressGeocodeResponse(
            id=cached["id"],
            original_address=cached["original_address"],
            normalized_address=cached["normalized_address"],
            latitude=cached["latitude"],
            longitude=cached["longitude"],
            geocoding_status=cached["geocoding_status"],
            geocoding_provider=cached["geocoding_provider"],
            confidence_score=(
                float(cached["confidence_score"])
                if cached["confidence_score"] is not None
                else None
            ),
            from_cache=True,
        )

    client = NominatimClient()
    candidates = await client.search(normalized.normalized_address, limit=3)

    if not candidates:
        return AddressGeocodeResponse(
            id=None,
            original_address=normalized.original_address,
            address_for_geocoding=normalized.address_for_geocoding,
            normalized_address=normalized.normalized_address,
            geocoding_status="not_found",
            geocoding_provider="nominatim",
            source="nominatim",
            error="Address was not found by geocoder",
        )

    best = candidates[0]

    status = "found"
    if len(candidates) > 1:
        second = candidates[1]
        if (
            best.importance is not None
            and second.importance is not None
            and abs(best.importance - second.importance) < 0.02
        ):
            status = "ambiguous"

    confidence_score = estimate_confidence_score(
        query=normalized.normalized_address,
        display_name=best.display_name,
        importance=best.importance,
    )

    saved = await upsert_address(
        db,
        original_address=normalized.original_address,
        normalized_address=normalized.normalized_address,
        latitude=best.latitude,
        longitude=best.longitude,
        geocoding_status=status,
        geocoding_provider="nominatim",
        confidence_score=confidence_score,
    )

    return AddressGeocodeResponse(
        id=saved["id"],
        original_address=saved["original_address"],
        normalized_address=saved["normalized_address"],
        latitude=saved["latitude"],
        longitude=saved["longitude"],
        geocoding_status=saved["geocoding_status"],
        geocoding_provider=saved["geocoding_provider"],
        confidence_score=(
            float(saved["confidence_score"])
            if saved["confidence_score"] is not None
            else None
        ),
        display_name=best.display_name,
        from_cache=False,
    )
