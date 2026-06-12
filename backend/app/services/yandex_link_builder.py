import re
from urllib.parse import urlencode

from app.schemas.yandex_links import (
    BuildYandexLinksRequest,
    BuildYandexLinksResponse,
    YandexLinkBatchInput,
    YandexLinkBatchResponse,
    YandexLinkPointInput,
)


DEFAULT_CITY_SLUG = "saint-petersburg"
DEFAULT_ROUTE_TYPE = "auto"
DEFAULT_ROUND_COORDINATES = 6
DEFAULT_MAX_URL_LENGTH = 2000
MANY_POINTS_WARNING_THRESHOLD = 20
YANDEX_MAPS_BASE_URL = "https://yandex.ru/maps/2"


class YandexLinkError(Exception):
    pass


class YandexLinkValidationError(YandexLinkError):
    pass


def format_coordinate(value: float, round_coordinates: int = DEFAULT_ROUND_COORDINATES) -> str:
    return f"{value:.{round_coordinates}f}"


def format_yandex_rtext_point(
    point: YandexLinkPointInput,
    round_coordinates: int = DEFAULT_ROUND_COORDINATES,
) -> str:
    return (
        f"{format_coordinate(point.latitude, round_coordinates)},"
        f"{format_coordinate(point.longitude, round_coordinates)}"
    )


def build_rtext(
    points: list[YandexLinkPointInput],
    round_coordinates: int = DEFAULT_ROUND_COORDINATES,
) -> str:
    return "~".join(
        format_yandex_rtext_point(point, round_coordinates)
        for point in points
    )


def calculate_center_point(points: list[YandexLinkPointInput]) -> tuple[float, float]:
    latitude = sum(point.latitude for point in points) / len(points)
    longitude = sum(point.longitude for point in points) / len(points)
    return latitude, longitude


def format_yandex_ll(
    center_point: tuple[float, float],
    round_coordinates: int = DEFAULT_ROUND_COORDINATES,
) -> str:
    latitude, longitude = center_point
    return (
        f"{format_coordinate(longitude, round_coordinates)},"
        f"{format_coordinate(latitude, round_coordinates)}"
    )


def build_ll(
    points: list[YandexLinkPointInput],
    round_coordinates: int = DEFAULT_ROUND_COORDINATES,
) -> str:
    return format_yandex_ll(
        calculate_center_point(points),
        round_coordinates,
    )


def build_yandex_maps_url(
    batch: YandexLinkBatchInput,
    *,
    city_slug: str = DEFAULT_CITY_SLUG,
    route_type: str = DEFAULT_ROUTE_TYPE,
    round_coordinates: int = DEFAULT_ROUND_COORDINATES,
) -> str:
    points = validate_batch_points(batch)
    city_slug = normalize_city_slug(city_slug)
    query = urlencode(
        {
            "ll": build_ll(points, round_coordinates),
            "mode": "routes",
            "rtext": build_rtext(points, round_coordinates),
            "rtn": "1",
            "rtt": route_type,
        }
    )

    return f"{YANDEX_MAPS_BASE_URL}/{city_slug}/?{query}"


def add_yandex_links_to_batches(
    payload: BuildYandexLinksRequest,
) -> BuildYandexLinksResponse:
    city_slug_defaulted = (
        "city_slug" not in payload.model_fields_set
        or not payload.city_slug.strip()
    )
    city_slug = normalize_city_slug(payload.city_slug)
    route_type = payload.route_type

    validate_city_slug(city_slug)
    validate_route_type(route_type)

    batches = validate_batches(payload.batches)

    response_batches: list[YandexLinkBatchResponse] = []
    has_any_warning = False

    for index, batch in enumerate(batches, start=1):
        normalized_batch = normalize_batch_number(batch, index)
        points = validate_batch_points(normalized_batch)
        warnings = batch_warnings(
            normalized_batch,
            points,
            city_slug_defaulted=city_slug_defaulted,
        )
        yandex_maps_url = build_yandex_maps_url(
            normalized_batch,
            city_slug=city_slug,
            route_type=route_type,
            round_coordinates=payload.round_coordinates,
        )
        url_length = len(yandex_maps_url)

        if url_length > payload.max_url_length:
            warnings.append("URL length exceeds recommended limit")

        has_warning = bool(warnings)
        has_any_warning = has_any_warning or has_warning

        response_batches.append(
            YandexLinkBatchResponse(
                batch_number=normalized_batch.batch_number or index,
                points_count=len(points),
                url_length=url_length,
                has_warning=has_warning,
                warnings=warnings,
                yandex_maps_url=yandex_maps_url,
                points=points,
            )
        )

    return BuildYandexLinksResponse(
        status="completed_with_warnings" if has_any_warning else "completed",
        city_slug=city_slug,
        route_type=route_type,
        batches_count=len(response_batches),
        batches=response_batches,
    )


def validate_batches(batches: list[YandexLinkBatchInput]) -> list[YandexLinkBatchInput]:
    if not batches:
        raise YandexLinkValidationError("batches must not be empty")

    normalized_numbers: list[int] = []
    for index, batch in enumerate(batches, start=1):
        batch_number = batch.batch_number or index
        normalized_numbers.append(batch_number)

    if len(set(normalized_numbers)) != len(normalized_numbers):
        raise YandexLinkValidationError("duplicate batch_number values")

    return batches


def normalize_batch_number(
    batch: YandexLinkBatchInput,
    fallback_number: int,
) -> YandexLinkBatchInput:
    return batch.model_copy(
        update={
            "batch_number": batch.batch_number or fallback_number,
        }
    )


def validate_batch_points(batch: YandexLinkBatchInput) -> list[YandexLinkPointInput]:
    if not batch.points:
        raise YandexLinkValidationError("batch points must not be empty")

    if len(batch.points) < 2:
        raise YandexLinkValidationError("batch must contain at least two points")

    orders = [point.batch_order for point in batch.points]
    if len(set(orders)) != len(orders):
        raise YandexLinkValidationError("duplicate batch_order values in batch")

    return sorted(batch.points, key=lambda point: point.batch_order)


def validate_city_slug(city_slug: str) -> None:
    if not re.fullmatch(r"[a-z0-9-]+", city_slug):
        raise YandexLinkValidationError("invalid city_slug")


def normalize_city_slug(city_slug: str | None) -> str:
    value = (city_slug or "").strip()
    return value or DEFAULT_CITY_SLUG


def validate_route_type(route_type: str) -> None:
    if route_type != DEFAULT_ROUTE_TYPE:
        raise YandexLinkValidationError("unsupported route_type")


def batch_warnings(
    batch: YandexLinkBatchInput,
    points: list[YandexLinkPointInput],
    *,
    city_slug_defaulted: bool,
) -> list[str]:
    warnings: list[str] = []

    if len(points) > MANY_POINTS_WARNING_THRESHOLD:
        warnings.append("Batch contains many points")

    if (
        batch.batch_number is not None
        and batch.batch_number > 1
        and not points[0].is_transition_point
    ):
        warnings.append("Transition point is missing")

    if city_slug_defaulted:
        warnings.append("City slug was not provided, default value used")

    return warnings
