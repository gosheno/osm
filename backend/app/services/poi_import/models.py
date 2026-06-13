from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class RegionBounds:
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float

    def contains(self, latitude: float, longitude: float) -> bool:
        return (
            self.min_lat <= latitude <= self.max_lat
            and self.min_lon <= longitude <= self.max_lon
        )


@dataclass(frozen=True)
class RegionConfig:
    name: str
    default_country: str
    bounds: RegionBounds
    allowed_regions: list[str]


@dataclass(frozen=True)
class ChainConfig:
    canonical_brand: str
    aliases: list[str]
    priority: int = 100


@dataclass(frozen=True)
class PoiImportConfig:
    region: RegionConfig
    chains: list[ChainConfig]


@dataclass
class PoiCandidate:
    osm_type: str
    osm_id: int
    canonical_brand: str
    detected_brand: str | None
    name: str | None
    operator: str | None
    shop_type: str | None
    amenity_type: str | None
    original_address: str | None
    normalized_address: str | None
    country: str = "Russia"
    region: str | None = None
    city: str | None = None
    district: str | None = None
    suburb: str | None = None
    street: str | None = None
    house_number: str | None = None
    postcode: str | None = None
    latitude: float = 0.0
    longitude: float = 0.0
    phone: str | None = None
    website: str | None = None
    opening_hours: str | None = None
    source: str = "osm_pbf"
    enrichment_source: str | None = None
    raw_tags: dict[str, Any] = field(default_factory=dict)
    confidence_score: float = 0.0
    warnings: list[str] = field(default_factory=list)
    is_duplicate: bool = False
    duplicate_of_key: tuple[str, int] | None = None
    duplicate_of_id: int | None = None

    @property
    def osm_key(self) -> tuple[str, int]:
        return (self.osm_type, self.osm_id)

