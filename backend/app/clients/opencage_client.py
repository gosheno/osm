from dataclasses import dataclass

import httpx

from app.core.config import settings


@dataclass(frozen=True)
class GeocodingCandidate:
    latitude: float
    longitude: float
    display_name: str
    confidence: int | None = None
    raw: dict | None = None


class OpenCageConfigError(Exception):
    pass


class OpenCageUnexpectedResponseError(Exception):
    pass


class OpenCageClient:
    def __init__(self) -> None:
        if not settings.OPENCAGE_API_KEY:
            raise OpenCageConfigError("OPENCAGE_API_KEY is not set")

        self.base_url = settings.OPENCAGE_BASE_URL.rstrip("/")

    async def search(self, query: str, limit: int | None = None) -> list[GeocodingCandidate]:
        params: dict[str, str | int] = {
            "q": query,
            "key": settings.OPENCAGE_API_KEY,
            "language": settings.OPENCAGE_LANGUAGE,
            "countrycode": settings.OPENCAGE_COUNTRYCODE,
            "limit": limit or settings.OPENCAGE_LIMIT,
        }

        if settings.OPENCAGE_NO_ANNOTATIONS:
            params["no_annotations"] = 1

        if settings.OPENCAGE_NO_RECORD:
            params["no_record"] = 1

        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(f"{self.base_url}/json", params=params)

        data = response.json()

        status = data.get("status", {})
        code = status.get("code")

        if response.status_code != 200 or code != 200:
            message = status.get("message") or data
            raise OpenCageUnexpectedResponseError(f"OpenCage error: {message}")

        results = data.get("results")
        if not isinstance(results, list):
            raise OpenCageUnexpectedResponseError("OpenCage returned invalid results")

        candidates: list[GeocodingCandidate] = []

        for item in results:
            if not isinstance(item, dict):
                continue

            geometry = item.get("geometry") or {}
            lat = geometry.get("lat")
            lng = geometry.get("lng")

            if lat is None or lng is None:
                continue

            try:
                candidates.append(
                    GeocodingCandidate(
                        latitude=float(lat),
                        longitude=float(lng),
                        display_name=item.get("formatted", ""),
                        confidence=(
                            int(item["confidence"])
                            if item.get("confidence") is not None
                            else None
                        ),
                        raw=item,
                    )
                )
            except (TypeError, ValueError):
                continue

        return candidates
