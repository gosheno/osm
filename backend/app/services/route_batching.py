from app.schemas.batching import (
    BatchPointInput,
    BatchRoutePoint,
    BatchRouteRequest,
    BatchRouteResponse,
    RouteBatch,
    RouteLegInput,
)


DEFAULT_BATCH_SIZE = 15
MAX_BATCH_SIZE = 20


class RouteBatchingError(Exception):
    pass


class InvalidBatchSizeError(RouteBatchingError):
    pass


class InvalidOrderedPointsError(RouteBatchingError):
    pass


class InvalidLegsError(RouteBatchingError):
    pass


def validate_batch_size(batch_size: int) -> int:
    if batch_size < 1 or batch_size > MAX_BATCH_SIZE:
        raise InvalidBatchSizeError("batch_size must be between 1 and 20")

    return batch_size


def validate_ordered_points(points: list[BatchPointInput]) -> list[BatchPointInput]:
    if len(points) < 2:
        raise InvalidOrderedPointsError(
            "ordered_points must contain at least start and end points"
        )

    orders = [point.order for point in points]
    if len(set(orders)) != len(orders):
        raise InvalidOrderedPointsError(
            "ordered_points contain duplicate order values"
        )

    sorted_points = sorted(points, key=lambda point: point.order)

    expected_orders = list(range(len(sorted_points)))
    if [point.order for point in sorted_points] != expected_orders:
        raise InvalidOrderedPointsError(
            "ordered_points order values must be sequential"
        )

    if sorted_points[0].type != "start":
        raise InvalidOrderedPointsError("First point must be start")

    if sorted_points[-1].type != "end":
        raise InvalidOrderedPointsError("Last point must be end")

    for point in sorted_points[1:-1]:
        if point.type == "start":
            raise InvalidOrderedPointsError(
                "Start point must not appear in the middle of route"
            )
        if point.type == "end":
            raise InvalidOrderedPointsError(
                "End point must not appear in the middle of route"
            )
        if point.type != "waypoint":
            raise InvalidOrderedPointsError(
                "Intermediate points must have type waypoint"
            )

    return sorted_points


def split_waypoints(
    ordered_points: list[BatchPointInput],
    batch_size: int,
) -> list[list[BatchPointInput]]:
    waypoints = ordered_points[1:-1]
    if any(point.district for point in waypoints):
        return split_waypoints_by_district(waypoints, batch_size)

    return [
        waypoints[index : index + batch_size]
        for index in range(0, len(waypoints), batch_size)
    ]


def split_waypoints_by_district(
    waypoints: list[BatchPointInput],
    batch_size: int,
) -> list[list[BatchPointInput]]:
    groups: list[list[BatchPointInput]] = []
    current_group: list[BatchPointInput] = []
    current_district: str | None = None

    for point in waypoints:
        point_district = point.district
        district_changed = (
            current_group
            and current_district is not None
            and point_district is not None
            and point_district != current_district
        )
        size_limit_reached = len(current_group) >= batch_size

        if district_changed or size_limit_reached:
            groups.append(current_group)
            current_group = []
            current_district = None

        current_group.append(point)

        if current_district is None and point_district is not None:
            current_district = point_district

    if current_group:
        groups.append(current_group)

    return groups


def validate_legs(
    ordered_points: list[BatchPointInput],
    legs: list[RouteLegInput] | None,
) -> dict[tuple[int, int], RouteLegInput] | None:
    if legs is None:
        return None

    expected_pairs = {
        (from_point.order, to_point.order)
        for from_point, to_point in zip(ordered_points, ordered_points[1:])
    }
    actual_pairs = [(leg.from_order, leg.to_order) for leg in legs]

    if len(set(actual_pairs)) != len(actual_pairs):
        raise InvalidLegsError("legs do not match ordered_points")

    if set(actual_pairs) != expected_pairs:
        raise InvalidLegsError("legs do not match ordered_points")

    return {
        (leg.from_order, leg.to_order): leg
        for leg in legs
    }


def calculate_batch_totals(
    batch_points: list[BatchPointInput],
    legs_by_pair: dict[tuple[int, int], RouteLegInput] | None,
) -> tuple[float | None, float | None]:
    if legs_by_pair is None:
        return None, None

    distance_m = 0.0
    duration_s = 0.0

    for from_point, to_point in zip(batch_points, batch_points[1:]):
        leg = legs_by_pair.get((from_point.order, to_point.order))
        if leg is None:
            raise InvalidLegsError("legs do not match ordered_points")

        distance_m += leg.distance_m
        duration_s += leg.duration_s

    return round(distance_m, 2), round(duration_s, 2)


def build_route_batches(
    ordered_points: list[BatchPointInput],
    *,
    batch_size: int,
    include_transition_point: bool,
    legs_by_pair: dict[tuple[int, int], RouteLegInput] | None,
) -> list[RouteBatch]:
    start_point = ordered_points[0]
    end_point = ordered_points[-1]
    waypoint_groups = split_waypoints(ordered_points, batch_size)

    if not waypoint_groups:
        waypoint_groups = [[]]

    batches: list[RouteBatch] = []

    for group_index, group in enumerate(waypoint_groups):
        is_first_batch = group_index == 0
        is_last_batch = group_index == len(waypoint_groups) - 1
        batch_points: list[BatchPointInput] = []
        transition_order: int | None = None

        if is_first_batch:
            batch_points.append(start_point)
        elif include_transition_point:
            previous_group = waypoint_groups[group_index - 1]
            transition_point = previous_group[-1]
            transition_order = transition_point.order
            batch_points.append(transition_point)

        batch_points.extend(group)

        if is_last_batch:
            batch_points.append(end_point)

        distance_m, duration_s = calculate_batch_totals(batch_points, legs_by_pair)

        batches.append(
            RouteBatch(
                batch_number=group_index + 1,
                points_count=len(batch_points),
                district=_batch_primary_district(batch_points, transition_order),
                districts=_batch_districts(batch_points, transition_order),
                distance_m=distance_m,
                duration_s=duration_s,
                points=_batch_points(batch_points, transition_order),
            )
        )

    return batches


def batch_optimized_route(payload: BatchRouteRequest) -> BatchRouteResponse:
    batch_size = validate_batch_size(payload.batch_size)
    ordered_points = validate_ordered_points(payload.ordered_points)
    legs_by_pair = validate_legs(ordered_points, payload.legs)
    batches = build_route_batches(
        ordered_points,
        batch_size=batch_size,
        include_transition_point=payload.include_transition_point,
        legs_by_pair=legs_by_pair,
    )

    return BatchRouteResponse(
        status="completed",
        batch_size=batch_size,
        total_points=len(ordered_points),
        batches_count=len(batches),
        batches=batches,
    )


def _batch_points(
    points: list[BatchPointInput],
    transition_order: int | None,
) -> list[BatchRoutePoint]:
    return [
        BatchRoutePoint(
            batch_order=index,
            global_order=point.order,
            type=point.type,
            label=point.label,
            latitude=point.latitude,
            longitude=point.longitude,
            original_index=point.original_index,
            district=point.district,
            is_transition_point=(
                index == 0
                and transition_order is not None
                and point.order == transition_order
            ),
        )
        for index, point in enumerate(points)
    ]


def _batch_districts(
    points: list[BatchPointInput],
    transition_order: int | None = None,
) -> list[str]:
    districts: list[str] = []

    for point in points:
        if transition_order is not None and point.order == transition_order:
            continue
        if point.type != "waypoint" or point.district is None:
            continue
        if point.district not in districts:
            districts.append(point.district)

    return districts


def _batch_primary_district(
    points: list[BatchPointInput],
    transition_order: int | None = None,
) -> str | None:
    districts = _batch_districts(points, transition_order)
    if len(districts) == 1:
        return districts[0]
    return None
