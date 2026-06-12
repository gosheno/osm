from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.geocoding import GeocodingContextInput


class AddressNormalizeRequest(BaseModel):
    address: str = Field(..., min_length=1)
    default_city: str | None = "санкт-петербург"
    place_name: str | None = None


class AddressNormalizeResponse(BaseModel):
    original_address: str
    address_for_geocoding: str
    normalized_address: str
    tokens: list[str]
    place_name: str | None = None


class AddressBulkNormalizeRequest(BaseModel):
    addresses: list[str] = Field(..., min_length=1)
    default_city: str | None = "санкт-петербург"


class AddressBulkNormalizeItem(BaseModel):
    original_address: str
    address_for_geocoding: str | None = None
    normalized_address: str | None = None
    tokens: list[str] = Field(default_factory=list)
    place_name: str | None = None
    status: str
    error: str | None = None


class AddressBulkNormalizeResponse(BaseModel):
    total: int
    items: list[AddressBulkNormalizeItem]


class AddressGeocodeRequest(BaseModel):
    address: str = Field(..., min_length=1)
    default_city: str | None = "санкт-петербург"
    place_name: str | None = None
    force_refresh: bool = False
    geocoding_context: GeocodingContextInput | None = None
    geocoding_area: str | None = None


class AddressGeocodeResponse(BaseModel):
    id: int | None = None
    original_address: str
    address_for_geocoding: str | None = None
    normalized_address: str
    place_name: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    geocoding_status: str
    geocoding_provider: str | None = None
    confidence_score: float | None = None
    geocoding_score: float | None = None
    source: str
    geocoding_query: str | None = None
    display_name: str | None = None
    geocoding_context_label: str | None = None
    geocoding_context_latitude: float | None = None
    geocoding_context_longitude: float | None = None
    geocoding_context_radius_km: float | None = None
    geocoding_context_source: str | None = None
    distance_to_context_m: float | None = None
    error: str | None = None


class AddressSuggestionItem(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    provider: str = "nominatim"
    display_name: str
    main_text: str
    secondary_text: str | None = None
    latitude: float
    longitude: float
    osm_type: str | None = None
    osm_id: int | None = None
    place_id: int | None = None
    category: str | None = Field(default=None, alias="class")
    type: str | None = None
    importance: float | None = None
    confidence_score: float | None = None
    address: dict[str, Any] = Field(default_factory=dict)
    geocoding_status: str = "found"
    source: str = "nominatim"
    outside_supported_region: bool = False


class AddressSuggestResponse(BaseModel):
    query: str
    normalized_query: str
    status: str
    items: list[AddressSuggestionItem] = Field(default_factory=list)
    error: str | None = None


class AddressConfirmCandidate(BaseModel):
    provider: str = "nominatim"
    display_name: str
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    osm_type: str | None = None
    osm_id: int | None = None
    place_id: int | None = None
    confidence_score: float | None = None
    geocoding_status: str | None = "found"
    address: dict[str, Any] = Field(default_factory=dict)
    raw: dict[str, Any] | None = None


class AddressConfirmRequest(BaseModel):
    original_query: str = Field(..., min_length=1)
    selected_candidate: AddressConfirmCandidate


class AddressConfirmResponse(BaseModel):
    status: str
    address_id: int
    latitude: float
    longitude: float
    geocoding_status: str
