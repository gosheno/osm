from pydantic import BaseModel, Field


class GeocodingQuery(BaseModel):
    query: str
    priority: int = 0
    region_hint: str | None = None
    settlement_hint: str | None = None
    note: str | None = None


class ParsedAddress(BaseModel):
    original_address: str
    place_name: str | None = None
    cleaned_address: str
    normalized_address: str
    normalized_key: str
    region_hint: str | None = None
    settlement_hint: str | None = None
    street: str | None = None
    house: str | None = None
    building: str | None = None
    corpus: str | None = None
    letter: str | None = None
    geocoding_queries: list[GeocodingQuery] = Field(default_factory=list)

    @property
    def original(self) -> str:
        return self.original_address

    @property
    def cleaned(self) -> str:
        return self.cleaned_address
