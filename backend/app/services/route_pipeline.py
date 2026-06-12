from dataclasses import dataclass
from typing import Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.osrm_client import OsrmClient
from app.core.config import settings
from app.schemas.batching import BatchPointInput, BatchRouteRequest, RouteLegInput
from app.schemas.optimization import CoordinateInput, OptimizeRouteRequest
from app.schemas.route import (
    FailedAddressResult,
    OptimizedRoutePointResult,
    OptimizeRouteByAddressesRequest,
    OptimizeRouteByAddressesResponse,
    RouteAddressResult,
    RouteAddressRole,
    RouteBatchPointResult,
    RouteBatchResult,
    RouteLegResult,
)
from app.schemas.yandex_links import (
    BuildYandexLinksRequest,
    YandexLinkBatchInput,
    YandexLinkPointInput,
)
from app.core.exceptions import AppError
from app.repositories.route_repository import save_route_batches
from app.services.address_service import AddressService
from app.services.route_batching import batch_optimized_route
from app.services.route_optimizer import build_optimized_route
from app.services.spb_districts import infer_spb_district
from app.services.yandex_link_builder import add_yandex_links_to_batches


AddressServiceFactory = Callable[[AsyncSession], AddressService]


class RoutePipelineError(Exception):
    pass


@dataclass(frozen=True)
class PreparedRouteAddress:
    role: RouteAddressRole
    input_index: int
    original_index: int
    address: str


def prepare_route_addresses(
    payload: OptimizeRouteByAddressesRequest,
) -> list[PreparedRouteAddress]:
    prepared = [
        PreparedRouteAddress(
            role="start",
            input_index=0,
            original_index=0,
            address=payload.start_address,
        )
    ]

    for input_index, address in enumerate(payload.addresses, start=1):
        prepared.append(
            PreparedRouteAddress(
                role="waypoint",
                input_index=input_index,
                original_index=input_index,
                address=address,
            )
        )

    end_index = len(payload.addresses) + 1
    prepared.append(
        PreparedRouteAddress(
            role="end",
            input_index=end_index,
            original_index=end_index,
            address=payload.end_address,
        )
    )

    return prepared


async def geocode_route_addresses(
    prepared_addresses: list[PreparedRouteAddress],
    payload: OptimizeRouteByAddressesRequest,
    db: AsyncSession,
    *,
    address_service_factory: AddressServiceFactory = AddressService,
) -> list[RouteAddressResult]:
    service = address_service_factory(db)
    results: list[RouteAddressResult] = []

    for prepared in prepared_addresses:
        selected = _selected_address_for_role(
            payload,
            prepared.role,
            prepared.input_index,
        )
        if selected is not None:
            results.append(route_address_from_selected(prepared, selected))
            continue

        try:
            result = await service.geocode_address(
                prepared.address,
                default_city=payload.default_city,
                force_refresh=payload.force_refresh,
                geocoding_context=payload.geocoding_context,
                geocoding_area=payload.geocoding_area,
            )
            results.append(route_address_from_geocode(prepared, result))
        except Exception as exc:
            rollback = getattr(db, "rollback", None)
            if rollback is not None:
                await rollback()
            results.append(
                RouteAddressResult(
                    role=prepared.role,
                    input_index=prepared.input_index,
                    original_index=prepared.original_index,
                    input_address=prepared.address,
                    geocoding_status="error",
                    geocoding_provider=settings.GEOCODER_PROVIDER.lower().strip(),
                    source=settings.GEOCODER_PROVIDER.lower().strip(),
                    error=str(exc),
                )
            )

    return results


def _selected_address_for_role(
    payload: OptimizeRouteByAddressesRequest,
    role: RouteAddressRole,
    input_index: int,
):
    if role == "start":
        return payload.start_selected
    if role == "end":
        return payload.end_selected
    if role == "waypoint":
        waypoint_index = input_index - 1
        if 0 <= waypoint_index < len(payload.waypoints_selected):
            return payload.waypoints_selected[waypoint_index]
    return None


def route_address_from_selected(
    prepared: PreparedRouteAddress,
    selected,
) -> RouteAddressResult:
    selected_status = selected.geocoding_status or "found"
    route_status = (
        selected_status
        if selected_status in {"not_found", "error"}
        else "found"
    )

    return RouteAddressResult(
        id=selected.address_id,
        role=prepared.role,
        input_index=prepared.input_index,
        original_index=prepared.original_index,
        input_address=prepared.address,
        original_address=selected.display_name,
        address_for_geocoding=selected.display_name,
        normalized_address=None,
        latitude=selected.latitude,
        longitude=selected.longitude,
        geocoding_status=route_status,
        geocoding_provider="nominatim",
        confidence_score=selected.confidence_score,
        source="selected",
        from_cache=False,
        error=None,
    )


def route_address_from_geocode(
    prepared: PreparedRouteAddress,
    result: dict,
) -> RouteAddressResult:
    return RouteAddressResult(
        id=result.get("id"),
        role=prepared.role,
        input_index=prepared.input_index,
        original_index=prepared.original_index,
        input_address=prepared.address,
        original_address=result.get("original_address"),
        address_for_geocoding=result.get("address_for_geocoding"),
        normalized_address=result.get("normalized_address"),
        place_name=result.get("place_name"),
        latitude=result.get("latitude"),
        longitude=result.get("longitude"),
        geocoding_status=result.get("geocoding_status"),
        geocoding_provider=result.get("geocoding_provider"),
        confidence_score=result.get("confidence_score"),
        geocoding_score=result.get("geocoding_score"),
        geocoding_query=result.get("geocoding_query"),
        geocoding_context_label=result.get("geocoding_context_label"),
        distance_to_context_m=result.get("distance_to_context_m"),
        source=result.get("source"),
        from_cache=result.get("source") == "database",
        error=result.get("error"),
    )


def validate_geocoding_results(
    geocoded_addresses: list[RouteAddressResult],
) -> list[FailedAddressResult]:
    failed_addresses: list[FailedAddressResult] = []

    for result in geocoded_addresses:
        if (
            result.latitude is not None
            and result.longitude is not None
            and result.geocoding_status in ("found", "manual")
        ):
            continue

        is_ambiguous = result.geocoding_status == "ambiguous"
        is_geocoder_error = result.geocoding_status == "error"

        failed_addresses.append(
            FailedAddressResult(
                type=result.role,
                input_index=result.input_index,
                original_index=result.original_index,
                input_address=result.input_address,
                address_for_geocoding=result.address_for_geocoding,
                normalized_address=result.normalized_address,
                place_name=result.place_name,
                geocoding_status=result.geocoding_status,
                geocoding_provider=result.geocoding_provider,
                geocoding_score=result.geocoding_score,
                geocoding_query=result.geocoding_query,
                geocoding_context_label=result.geocoding_context_label,
                source=result.source,
                error=(
                    result.error
                    or (
                        "Address was resolved ambiguously"
                        if is_ambiguous
                        else "Address coordinates were not found"
                    )
                ),
                reason=(
                    "Адрес найден неоднозначно. Проверьте область поиска или уточните дом."
                    if is_ambiguous
                    else result.error
                    if is_geocoder_error and result.error
                    else "Сбой геокодера. Проверьте настройки провайдера или повторите попытку."
                    if is_geocoder_error
                    else "Адрес не найден геокодером."
                ),
                code=(
                    "ADDRESS_AMBIGUOUS"
                    if is_ambiguous
                    else "ADDRESS_GEOCODER_ERROR"
                    if is_geocoder_error
                    else "ADDRESS_NOT_FOUND"
                ),
            )
        )

    return failed_addresses


def build_points_for_optimization(
    geocoded_addresses: list[RouteAddressResult],
) -> OptimizeRouteRequest:
    start = _address_by_role(geocoded_addresses, "start")
    end = _address_by_role(geocoded_addresses, "end")
    waypoints = [
        address for address in geocoded_addresses if address.role == "waypoint"
    ]

    return OptimizeRouteRequest(
        start=_coordinate_input(start),
        end=_coordinate_input(end),
        points=[_coordinate_input(address) for address in waypoints],
    )


async def run_route_optimization(
    payload: OptimizeRouteByAddressesRequest,
    geocoded_addresses: list[RouteAddressResult],
    *,
    osrm_client: OsrmClient | None = None,
):
    optimization_payload = build_points_for_optimization(geocoded_addresses)
    optimization_payload = optimization_payload.model_copy(
        update={"optimization_metric": payload.optimization_metric}
    )
    return await build_optimized_route(
        optimization_payload,
        osrm_client=osrm_client,
    )


def run_route_batching(
    payload: OptimizeRouteByAddressesRequest,
    optimization_result,
    geocoded_addresses: list[RouteAddressResult],
):
    address_by_original_index = {
        address.original_index: address for address in geocoded_addresses
    }

    return batch_optimized_route(
        BatchRouteRequest(
            ordered_points=[
                _batch_point_input(point, address_by_original_index)
                for point in optimization_result.ordered_points
            ],
            legs=[
                RouteLegInput(**leg.model_dump())
                for leg in optimization_result.legs
            ],
            batch_size=payload.batch_size,
        )
    )


def run_yandex_link_generation(
    payload: OptimizeRouteByAddressesRequest,
    batching_result,
):
    return add_yandex_links_to_batches(
        BuildYandexLinksRequest(
            city_slug=payload.city_slug,
            batches=[
                YandexLinkBatchInput(
                    batch_number=batch.batch_number,
                    points=[
                        YandexLinkPointInput(**point.model_dump())
                        for point in batch.points
                    ],
                )
                for batch in batching_result.batches
            ],
        )
    )


async def fetch_route_geometry(
    optimization_result,
    *,
    osrm_client: OsrmClient | None = None,
) -> dict | None:
    if not getattr(optimization_result, "ordered_points", None):
        return None

    client = osrm_client or OsrmClient()
    get_route = getattr(client, "get_route", None)
    if get_route is None:
        return None

    try:
        route = await get_route(
            optimization_result.ordered_points,
            overview=True,
            steps=False,
        )
    except Exception:
        return None

    geometry = route.get("geometry") if isinstance(route, dict) else None
    if not _is_linestring_geometry(geometry):
        return None

    return geometry


def _is_linestring_geometry(geometry) -> bool:
    if not isinstance(geometry, dict):
        return False
    if geometry.get("type") != "LineString":
        return False

    coordinates = geometry.get("coordinates")
    if not isinstance(coordinates, list) or len(coordinates) < 2:
        return False

    for coordinate in coordinates:
        if not isinstance(coordinate, (list, tuple)) or len(coordinate) < 2:
            return False
        try:
            longitude = float(coordinate[0])
            latitude = float(coordinate[1])
        except (TypeError, ValueError):
            return False
        if not -180 <= longitude <= 180 or not -90 <= latitude <= 90:
            return False

    return True


async def optimize_route_by_addresses(
    payload: OptimizeRouteByAddressesRequest,
    db: AsyncSession,
    *,
    address_service_factory: AddressServiceFactory = AddressService,
    osrm_client: OsrmClient | None = None,
) -> OptimizeRouteByAddressesResponse:
    prepared_addresses = prepare_route_addresses(payload)
    geocoded_addresses = await geocode_route_addresses(
        prepared_addresses,
        payload,
        db,
        address_service_factory=address_service_factory,
    )
    failed_addresses = validate_geocoding_results(geocoded_addresses)

    if failed_addresses:
        return build_failed_response(
            payload,
            geocoded_addresses,
            failed_addresses,
        )

    optimization_result = await run_route_optimization(
        payload,
        geocoded_addresses,
        osrm_client=osrm_client,
    )
    batching_result = run_route_batching(
        payload,
        optimization_result,
        geocoded_addresses,
    )
    route_geometry = await fetch_route_geometry(
        optimization_result,
        osrm_client=osrm_client,
    )
    yandex_result = run_yandex_link_generation(payload, batching_result)
    route_job_id = await persist_route_result(
        db,
        optimization_result,
        batching_result,
        yandex_result,
        geocoded_addresses,
    )

    return build_final_route_response(
        payload,
        geocoded_addresses,
        optimization_result,
        batching_result,
        yandex_result,
        route_job_id,
        route_geometry=route_geometry,
    )


def build_failed_response(
    payload: OptimizeRouteByAddressesRequest,
    geocoded_addresses: list[RouteAddressResult],
    failed_addresses: list[FailedAddressResult],
) -> OptimizeRouteByAddressesResponse:
    raise AppError(
        code=_failed_address_code(failed_addresses),
        message=_failed_address_message(failed_addresses),
        details="Некоторые адреса не удалось геокодировать.",
        status_code=400,
        failed_addresses=[address.model_dump() for address in failed_addresses],
        warnings=["Маршрут не построен, потому что часть адресов не удалось геокодировать."],
    )


def _failed_address_code(failed_addresses: list[FailedAddressResult]) -> str:
    if any(address.code == "ADDRESS_AMBIGUOUS" for address in failed_addresses):
        return "ADDRESS_REVIEW_REQUIRED"
    if any(address.code == "ADDRESS_GEOCODER_ERROR" for address in failed_addresses):
        return "GEOCODER_ERROR"

    has_start = any(address.type == "start" for address in failed_addresses)
    has_end = any(address.type == "end" for address in failed_addresses)
    has_waypoints = any(address.type == "waypoint" for address in failed_addresses)

    if has_start and not (has_end or has_waypoints):
        return "START_ADDRESS_NOT_FOUND"
    if has_end and not (has_start or has_waypoints):
        return "END_ADDRESS_NOT_FOUND"
    if has_waypoints and not (has_start or has_end):
        return "WAYPOINT_ADDRESS_NOT_FOUND"
    return "ADDRESS_NOT_FOUND"


def _failed_address_message(failed_addresses: list[FailedAddressResult]) -> str:
    if any(address.code == "ADDRESS_AMBIGUOUS" for address in failed_addresses):
        return "Некоторые адреса найдены неоднозначно."
    if any(address.code == "ADDRESS_GEOCODER_ERROR" for address in failed_addresses):
        return "Не удалось выполнить резервное геокодирование."

    has_start = any(address.type == "start" for address in failed_addresses)
    has_end = any(address.type == "end" for address in failed_addresses)
    has_waypoints = any(address.type == "waypoint" for address in failed_addresses)

    if has_start and not (has_end or has_waypoints):
        return "Начальный адрес не найден."
    if has_end and not (has_start or has_waypoints):
        return "Конечный адрес не найден."
    if has_waypoints and not (has_start or has_end):
        return "Один или несколько промежуточных адресов не найдены."
    return "Некоторые адреса не удалось обработать."


def build_final_route_response(
    payload: OptimizeRouteByAddressesRequest,
    geocoded_addresses: list[RouteAddressResult],
    optimization_result,
    batching_result,
    yandex_result,
    route_job_id: int | None = None,
    route_geometry: dict | None = None,
) -> OptimizeRouteByAddressesResponse:
    address_by_original_index = {
        address.original_index: address for address in geocoded_addresses
    }
    yandex_batches_by_number = {
        batch.batch_number: batch for batch in yandex_result.batches
    }
    warnings = collect_warnings(yandex_result)

    return OptimizeRouteByAddressesResponse(
        status=yandex_result.status,
        route_job_id=route_job_id,
        total_input_addresses=len(payload.addresses),
        total_addresses=len(payload.addresses),
        total_points=optimization_result.points_count,
        total_distance_m=optimization_result.total_distance_m,
        total_duration_s=optimization_result.total_duration_s,
        optimization_metric=payload.optimization_metric,
        batch_size=batching_result.batch_size,
        city_slug=yandex_result.city_slug,
        geocoded_addresses=geocoded_addresses,
        failed_addresses=[],
        ordered_points=[
            OptimizedRoutePointResult(
                **point.model_dump(),
                address=address_by_original_index.get(point.original_index),
                district=_point_district(
                    point,
                    address_by_original_index.get(point.original_index),
                ),
            )
            for point in optimization_result.ordered_points
        ],
        route_geometry=route_geometry,
        legs=[
            RouteLegResult(**leg.model_dump())
            for leg in optimization_result.legs
        ],
        batches=[
            merge_batch_with_yandex(batch, yandex_batches_by_number.get(batch.batch_number))
            for batch in batching_result.batches
        ],
        warnings=warnings,
    )


async def persist_route_result(
    db: AsyncSession | None,
    optimization_result,
    batching_result,
    yandex_result,
    geocoded_addresses: list[RouteAddressResult],
) -> int | None:
    if db is None:
        return None

    yandex_batches_by_number = {
        batch.batch_number: batch for batch in yandex_result.batches
    }

    return await save_route_batches(
        db,
        total_distance_m=optimization_result.total_distance_m,
        total_duration_s=optimization_result.total_duration_s,
        batches=batching_result.batches,
        yandex_batches_by_number=yandex_batches_by_number,
        ordered_points=optimization_result.ordered_points,
        legs=optimization_result.legs,
        geocoded_addresses=geocoded_addresses,
    )


def collect_warnings(yandex_result) -> list[str]:
    warnings: list[str] = []

    for batch in yandex_result.batches:
        for warning in batch.warnings:
            if warning not in warnings:
                warnings.append(warning)

    return warnings


def merge_batch_with_yandex(batch, yandex_batch) -> RouteBatchResult:
    return RouteBatchResult(
        batch_number=batch.batch_number,
        points_count=batch.points_count,
        district=batch.district,
        districts=batch.districts,
        distance_m=batch.distance_m,
        duration_s=batch.duration_s,
        url_length=yandex_batch.url_length if yandex_batch is not None else None,
        has_warning=yandex_batch.has_warning if yandex_batch is not None else False,
        warnings=yandex_batch.warnings if yandex_batch is not None else [],
        yandex_maps_url=(
            yandex_batch.yandex_maps_url if yandex_batch is not None else None
        ),
        points=[
            RouteBatchPointResult(**point.model_dump())
            for point in batch.points
        ],
    )


def _batch_point_input(
    point,
    address_by_original_index: dict[int, RouteAddressResult],
) -> BatchPointInput:
    address = address_by_original_index.get(point.original_index)

    return BatchPointInput(
        **point.model_dump(),
        district=_point_district(point, address),
    )


def _point_district(point, address: RouteAddressResult | None) -> str | None:
    return infer_spb_district(
        latitude=point.latitude,
        longitude=point.longitude,
        address_text=_district_address_text(address, point.label),
    )


def _district_address_text(
    address: RouteAddressResult | None,
    fallback_label: str | None,
) -> str:
    if address is None:
        return fallback_label or ""

    return " ".join(
        value
        for value in (
            address.input_address,
            address.original_address,
            address.normalized_address,
            address.address_for_geocoding,
            fallback_label,
        )
        if value
    )


def _address_by_role(
    geocoded_addresses: list[RouteAddressResult],
    role: RouteAddressRole,
) -> RouteAddressResult:
    for address in geocoded_addresses:
        if address.role == role:
            return address

    raise RoutePipelineError(f"{role} address is missing")


def _coordinate_input(address: RouteAddressResult) -> CoordinateInput:
    if address.latitude is None or address.longitude is None:
        raise RoutePipelineError(f"Coordinates are missing for {address.input_address}")

    return CoordinateInput(
        latitude=address.latitude,
        longitude=address.longitude,
        label=address.input_address,
    )
