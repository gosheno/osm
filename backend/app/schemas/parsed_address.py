from typing import List, Optional
from pydantic import BaseModel


class GeocodingQuery(BaseModel):
    query: str
    priority: int = 0
    region_hint: Optional[str] = None
    note: Optional[str] = None


class ParsedAddress(BaseModel):
    original: str
    cleaned: str
    normalized_key: str
    region_hint: Optional[str] = None
    settlement_hint: Optional[str] = None
    street: Optional[str] = None
    house: Optional[str] = None
    building: Optional[str] = None
    geocoding_queries: List[GeocodingQuery] = []
