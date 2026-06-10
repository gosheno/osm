from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class GeocodingCandidate:
    latitude: float
    longitude: float
    display_name: str
    importance: float | None = None
    place_rank: int | None = None
    raw: dict | None = None


class NominatimAccessDeniedError(Exception):
    pass


class NominatimUnexpectedResponseError(Exception):
    pass


class NominatimClient:
    def __init__(self) -> None:
        self.base_url = settings.NOMINATIM_BASE_URL.rstrip("/")
        self.headers = {
            "User-Agent": settings.NOMINATIM_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "ru,en;q=0.8",
        }

    async def search(self, query: str, limit: int = 1) -> list[GeocodingCandidate]:
        params: dict[str, str | int] = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": limit,
            "countrycodes": settings.country_codes,
        }

        if settings.NOMINATIM_EMAIL:
            params["email"] = settings.NOMINATIM_EMAIL

        async with httpx.AsyncClient(timeout=20.0, headers=self.headers) as client:
            response = await client.get(
                f"{self.base_url}/search",
                params=params,
            )

        if response.status_code == 403:
            raise NominatimAccessDeniedError(
                "Nominatim rejected the request with 403 Forbidden. "
                "Check User-Agent, email, usage policy, or use another/local geocoder."
            )

        response.raise_for_status()

        data = response.json()

        if isinstance(data, dict):
            raise NominatimUnexpectedResponseError(
                f"Nominatim returned object instead of list: {data}"
            )

        if not isinstance(data, list):
            raise NominatimUnexpectedResponseError(
                f"Nominatim returned unexpected response type: {type(data).__name__}"
            )

        candidates: list[GeocodingCandidate] = []

        for item in data:
            if not isinstance(item, dict):
                continue

            lat = item.get("lat")
            lon = item.get("lon")

            if lat is None or lon is None:
                continue

            try:
                importance_raw = item.get("importance")
                place_rank_raw = item.get("place_rank")

                candidates.append(
                    GeocodingCandidate(
                        latitude=float(lat),
                        longitude=float(lon),
                        display_name=item.get("display_name", ""),
                        importance=(
                            float(importance_raw)
                            if importance_raw is not None
                            else None
                        ),
                        place_rank=(
                            int(place_rank_raw)
                            if place_rank_raw is not None
                            else None
                        ),
                        raw=item,
                    )
                )
            except (TypeError, ValueError):
                continue

        return candidates
