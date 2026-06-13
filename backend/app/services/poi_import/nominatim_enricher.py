from __future__ import annotations

import json
from dataclasses import dataclass
from urllib.parse import urlencode, urlparse
from urllib.request import urlopen

from app.services.poi_import.address_normalizer import (
    build_address,
    normalized_known_poi_address,
)
from app.services.poi_import.models import PoiCandidate


@dataclass(frozen=True)
class NominatimEnricher:
    base_url: str
    timeout_s: float = 10.0

    def __post_init__(self) -> None:
        parsed = urlparse(self.base_url)
        if parsed.hostname == "nominatim.openstreetmap.org":
            raise ValueError("Public Nominatim must not be used for POI import")

    def enrich_if_needed(self, candidate: PoiCandidate) -> PoiCandidate:
        if candidate.street and candidate.house_number:
            return candidate

        query = urlencode(
            {
                "format": "jsonv2",
                "lat": candidate.latitude,
                "lon": candidate.longitude,
                "addressdetails": 1,
                "extratags": 1,
                "namedetails": 1,
            }
        )
        url = f"{self.base_url.rstrip('/')}/reverse?{query}"
        with urlopen(url, timeout=self.timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))

        address = payload.get("address") if isinstance(payload.get("address"), dict) else {}
        if not isinstance(address, dict):
            return candidate

        candidate.city = candidate.city or address.get("city") or address.get("town") or address.get("village")
        candidate.region = candidate.region or address.get("state") or address.get("region")
        candidate.suburb = candidate.suburb or address.get("suburb")
        candidate.district = candidate.district or address.get("district") or address.get("county")
        candidate.street = candidate.street or address.get("road") or address.get("pedestrian")
        candidate.house_number = candidate.house_number or address.get("house_number")
        candidate.postcode = candidate.postcode or address.get("postcode")

        if not candidate.original_address:
            candidate.original_address = build_address(
                {
                    "city": candidate.city,
                    "street": candidate.street,
                    "house_number": candidate.house_number,
                    "place": address.get("neighbourhood"),
                    "full": payload.get("display_name"),
                }
            )
            candidate.normalized_address = normalized_known_poi_address(
                candidate.original_address,
                default_city=candidate.city,
            )
        candidate.enrichment_source = "nominatim_reverse"
        return candidate

