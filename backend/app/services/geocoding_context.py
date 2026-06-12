from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class GeocodingContext:
    label: str
    latitude: float
    longitude: float
    radius_km: float
    source: str
    bounded: bool = False
    type: str = "custom_area"


SPB_LABEL = "Санкт-Петербург"
LENOBL_LABEL = "Ленинградская область"

DEFAULT_SPB_CONTEXT = GeocodingContext(
    label=SPB_LABEL,
    latitude=59.9386,
    longitude=30.3141,
    radius_km=60.0,
    source="default",
    bounded=False,
    type="default_spb",
)

SPB_LENOBL_CONTEXT = GeocodingContext(
    label=f"{SPB_LABEL} и ближайшая {LENOBL_LABEL}",
    latitude=59.9386,
    longitude=30.3141,
    radius_km=120.0,
    source="default",
    bounded=False,
    type="spb_lenobl",
)

SPB_ALIASES = {
    "спб",
    "с-пб",
    "санкт-петербург",
    "санкт петербург",
    "петербург",
    "питер",
}

SPB_SETTLEMENTS = {
    "колпино": (59.7507, 30.5886, 15.0),
    "пушкин": (59.7200, 30.4167, 15.0),
    "павловск": (59.6833, 30.4347, 15.0),
    "петергоф": (59.8845, 29.8852, 15.0),
    "ломоносов": (59.9107, 29.7725, 15.0),
    "кронштадт": (59.9911, 29.7775, 15.0),
    "сестрорецк": (60.0939, 29.9580, 15.0),
    "зеленогорск": (60.1997, 29.7018, 15.0),
    "красное село": (59.7383, 30.0867, 15.0),
    "шушары": (59.8092, 30.3760, 12.0),
    "парголово": (60.0813, 30.2642, 12.0),
    "песочный": (60.1231, 30.1640, 12.0),
    "левашово": (60.1030, 30.2090, 12.0),
}

LENOBL_SETTLEMENTS = {
    "мурино": (60.0444, 30.4486, 12.0),
    "кудрово": (59.9078, 30.5128, 12.0),
    "всеволожск": (60.0191, 30.6457, 18.0),
    "бугры": (60.0711, 30.3917, 10.0),
    "новое девяткино": (60.0617, 30.4806, 10.0),
    "янино": (59.9486, 30.5586, 10.0),
    "янино-1": (59.9486, 30.5586, 10.0),
    "колтуши": (59.9294, 30.6442, 10.0),
    "сертолово": (60.1444, 30.2119, 15.0),
    "токсово": (60.1539, 30.5169, 15.0),
    "гатчина": (59.5650, 30.1281, 20.0),
    "тосно": (59.5408, 30.8775, 20.0),
    "кириши": (59.4471, 32.0205, 20.0),
    "выборг": (60.7131, 28.7329, 20.0),
    "кировск": (59.8753, 30.9815, 15.0),
    "отрадное": (59.7728, 30.7944, 12.0),
    "шлиссельбург": (59.9444, 31.0339, 12.0),
    "приозерск": (61.0331, 30.1588, 20.0),
}

# Broad MVP working zone for Saint Petersburg and Leningrad Oblast.
WORK_AREA = {
    "min_lat": 58.30,
    "max_lat": 61.40,
    "min_lon": 27.20,
    "max_lon": 35.80,
}


def normalize_context_label(value: str | None) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[,.]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def build_default_context() -> GeocodingContext:
    return DEFAULT_SPB_CONTEXT


def build_spb_lenobl_context() -> GeocodingContext:
    return SPB_LENOBL_CONTEXT


def resolve_context_from_area(area: str | None) -> GeocodingContext:
    label = (area or "").strip()
    normalized = normalize_context_label(label)

    if not normalized:
        return build_default_context()

    if normalized in SPB_ALIASES:
        return build_default_context()

    for name, (latitude, longitude, radius_km) in SPB_SETTLEMENTS.items():
        if name in normalized:
            return GeocodingContext(
                label=name.title(),
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                source="user_area",
                bounded=True,
                type="district",
            )

    for name, (latitude, longitude, radius_km) in LENOBL_SETTLEMENTS.items():
        if name in normalized:
            return GeocodingContext(
                label=name.title(),
                latitude=latitude,
                longitude=longitude,
                radius_km=radius_km,
                source="user_area",
                bounded=True,
                type="district",
            )

    return GeocodingContext(
        label=label,
        latitude=DEFAULT_SPB_CONTEXT.latitude,
        longitude=DEFAULT_SPB_CONTEXT.longitude,
        radius_km=DEFAULT_SPB_CONTEXT.radius_km,
        source="user_area",
        bounded=True,
        type="custom_area",
    )


def build_context(
    geocoding_context: Any | None = None,
    geocoding_area: str | None = None,
) -> GeocodingContext:
    if geocoding_area:
        return resolve_context_from_area(geocoding_area)

    if geocoding_context is None:
        return build_default_context()

    data = (
        geocoding_context.model_dump(exclude_none=True)
        if hasattr(geocoding_context, "model_dump")
        else dict(geocoding_context)
    )
    context_type = data.get("type")

    if context_type == "spb_lenobl":
        return build_spb_lenobl_context()

    if context_type == "default_spb":
        return build_default_context()

    if context_type in {"district", "custom_area"} and data.get("label"):
        if data.get("latitude") is None or data.get("longitude") is None:
            return resolve_context_from_area(data["label"])

    if data.get("latitude") is not None and data.get("longitude") is not None:
        return GeocodingContext(
            label=data.get("label") or DEFAULT_SPB_CONTEXT.label,
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            radius_km=float(data.get("radius_km") or DEFAULT_SPB_CONTEXT.radius_km),
            source=data.get("source") or "custom_point",
            bounded=bool(data.get("bounded", False)),
            type=context_type or "custom_area",
        )

    return build_default_context()


def build_viewbox(context: GeocodingContext) -> str:
    lat_delta = context.radius_km / 111.0
    cos_lat = max(math.cos(math.radians(context.latitude)), 0.01)
    lon_delta = context.radius_km / (111.0 * cos_lat)

    min_lat = context.latitude - lat_delta
    max_lat = context.latitude + lat_delta
    min_lon = context.longitude - lon_delta
    max_lon = context.longitude + lon_delta

    # Nominatim expects longitude,latitude order.
    return f"{min_lon:.6f},{min_lat:.6f},{max_lon:.6f},{max_lat:.6f}"


def haversine_distance_m(
    latitude_a: float,
    longitude_a: float,
    latitude_b: float,
    longitude_b: float,
) -> float:
    earth_radius_m = 6_371_000.0
    phi_a = math.radians(latitude_a)
    phi_b = math.radians(latitude_b)
    delta_phi = math.radians(latitude_b - latitude_a)
    delta_lambda = math.radians(longitude_b - longitude_a)

    a = (
        math.sin(delta_phi / 2) ** 2
        + math.cos(phi_a) * math.cos(phi_b) * math.sin(delta_lambda / 2) ** 2
    )
    return earth_radius_m * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


def distance_to_context(
    latitude: float,
    longitude: float,
    context: GeocodingContext,
) -> float:
    return haversine_distance_m(
        latitude,
        longitude,
        context.latitude,
        context.longitude,
    )


def is_within_work_area(latitude: float, longitude: float) -> bool:
    return (
        WORK_AREA["min_lat"] <= latitude <= WORK_AREA["max_lat"]
        and WORK_AREA["min_lon"] <= longitude <= WORK_AREA["max_lon"]
    )
