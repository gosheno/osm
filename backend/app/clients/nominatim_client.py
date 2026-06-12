import asyncio
from dataclasses import dataclass
import time

import httpx

from app.core.config import settings
from app.services.geocoding_context import GeocodingContext, build_viewbox


@dataclass(frozen=True)
class GeocodingCandidate:
    latitude: float
    longitude: float
    display_name: str
    importance: float | None = None
    place_rank: int | None = None
    raw: dict | None = None


@dataclass(frozen=True)
class NominatimHealth:
    available: bool
    status_code: int | None
    response_time_ms: float
    body: str | None = None
    error: str | None = None


class NominatimAccessDeniedError(Exception):
    pass


class NominatimRateLimitError(Exception):
    pass


class NominatimUnexpectedResponseError(Exception):
    pass


class NominatimClient:
    _rate_limit_lock = asyncio.Lock()
    _last_request_at = 0.0

    def __init__(self) -> None:
        self.base_url = settings.NOMINATIM_BASE_URL.rstrip("/")
        self.headers = {
            "User-Agent": settings.NOMINATIM_USER_AGENT,
            "Accept": "application/json",
            "Accept-Language": "ru,en;q=0.8",
        }

    async def health_check(self) -> NominatimHealth:
        started_at = time.perf_counter()

        try:
            async with httpx.AsyncClient(
                timeout=settings.NOMINATIM_TIMEOUT_S,
                headers=self.headers,
            ) as client:
                response = await client.get(f"{self.base_url}/status")
        except httpx.HTTPError as exc:
            return NominatimHealth(
                available=False,
                status_code=None,
                response_time_ms=round((time.perf_counter() - started_at) * 1000, 2),
                error=str(exc),
            )

        response_time_ms = round((time.perf_counter() - started_at) * 1000, 2)
        body = response.text[:500] if response.text else None

        return NominatimHealth(
            available=200 <= response.status_code < 300,
            status_code=response.status_code,
            response_time_ms=response_time_ms,
            body=body,
            error=None if 200 <= response.status_code < 300 else body,
        )

    async def search(
        self,
        query: str,
        limit: int = 5,
        context: GeocodingContext | None = None,
        *,
        language: str | None = None,
        viewbox: str | None = None,
        bounded: bool | None = None,
    ) -> list[GeocodingCandidate]:
        params: dict[str, str | int] = {
            "q": query,
            "format": "jsonv2",
            "addressdetails": 1,
            "limit": limit,
            "countrycodes": settings.country_codes,
            "accept-language": language or settings.NOMINATIM_ACCEPT_LANGUAGE,
        }

        if viewbox:
            params["viewbox"] = viewbox
            params["bounded"] = 1 if bounded else 0
        elif context is not None:
            params["viewbox"] = build_viewbox(context)
            params["bounded"] = 1 if context.bounded else 0
        elif settings.NOMINATIM_DEFAULT_VIEWBOX:
            params["viewbox"] = settings.NOMINATIM_DEFAULT_VIEWBOX
            params["bounded"] = 1 if settings.NOMINATIM_DEFAULT_BOUNDED else 0

        if settings.NOMINATIM_EMAIL:
            params["email"] = settings.NOMINATIM_EMAIL

        async with httpx.AsyncClient(
            timeout=settings.NOMINATIM_TIMEOUT_S,
            headers=self.headers,
        ) as client:
            min_request_interval_s = max(
                float(settings.NOMINATIM_MIN_REQUEST_INTERVAL_S),
                0.0,
            )
            if min_request_interval_s <= 0:
                response = await client.get(
                    f"{self.base_url}/search",
                    params=params,
                )
            else:
                response = await self._rate_limited_get(
                    client,
                    f"{self.base_url}/search",
                    params=params,
                    min_request_interval_s=min_request_interval_s,
                )

        if response.status_code == 403:
            raise NominatimAccessDeniedError(
                "Nominatim rejected the request with 403 Forbidden. "
                "Check User-Agent, email, usage policy, or use another/local geocoder."
            )

        if response.status_code == 429:
            raise NominatimRateLimitError(
                "Nominatim rejected the request with 429 Too Many Requests. "
                "Retry later or use a local/geocoding provider with a higher limit."
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

    async def _rate_limited_get(
        self,
        client: httpx.AsyncClient,
        url: str,
        *,
        params: dict[str, str | int],
        min_request_interval_s: float,
    ) -> httpx.Response:
        async with self.__class__._rate_limit_lock:
            elapsed = time.monotonic() - self.__class__._last_request_at
            wait_s = min_request_interval_s - elapsed
            if wait_s > 0:
                await asyncio.sleep(wait_s)

            response = await client.get(url, params=params)
            self.__class__._last_request_at = time.monotonic()

        return response
