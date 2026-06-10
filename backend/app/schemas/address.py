from pydantic import BaseModel, Field


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
    tokens: list[str] = []
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
    source: str
    display_name: str | None = None
    error: str | None = None
