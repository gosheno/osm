import math
from typing import Literal

from app.clients.osrm_client import OsrmClient
from app.schemas.optimization import (
    CoordinateInput,
    OptimizationMetric,
    OptimizationPoint,
    OptimizeRouteRequest,
    OptimizeRouteResponse,
    OptimizedRouteLeg,
    OrderedRoutePoint,
)


MAX_INTERMEDIATE_POINTS = 100
MAX_TOTAL_POINTS = 102
TWO_OPT_MAX_ITERATIONS = 100
MATRIX_DIAGONAL_TOLERANCE = 1.0
IMPROVEMENT_TOLERANCE = 1e-9


class RouteOptimizationError(Exception):
    pass


class TooManyPointsError(RouteOptimizationError):
    pass


class InvalidMatrixError(RouteOptimizationError):
    pass


class UnreachableRouteError(RouteOptimizationError):
    pass


def validate_matrix(
    matrix: list[list[float | None]] | None,
    size: int,
    matrix_name: Literal["duration", "distance"],
) -> None:
    if not isinstance(matrix, list) or len(matrix) != size:
        raise InvalidMatrixError(f"OSRM returned invalid {matrix_name} matrix")

    for row_index, row in enumerate(matrix):
        if not isinstance(row, list) or len(row) != size:
            raise InvalidMatrixError(f"OSRM returned invalid {matrix_name} matrix")

        for column_index, value in enumerate(row):
            if value is None:
                raise UnreachableRouteError("Some points are unreachable by car route")

            if not isinstance(value, (int, float)) or not math.isfinite(value):
                raise InvalidMatrixError(
                    f"OSRM returned invalid {matrix_name} matrix"
                )

            if value < 0:
                raise InvalidMatrixError(
                    f"OSRM returned invalid {matrix_name} matrix"
                )

            if (
                row_index == column_index
                and abs(value) > MATRIX_DIAGONAL_TOLERANCE
            ):
                raise InvalidMatrixError(
                    f"OSRM returned invalid {matrix_name} matrix"
                )


def validate_matrices(
    durations: list[list[float | None]] | None,
    distances: list[list[float | None]] | None,
    size: int,
) -> None:
    validate_matrix(durations, size, "duration")
    validate_matrix(distances, size, "distance")


def calculate_route_cost(
    order: list[int],
    matrix: list[list[float | None]],
) -> float:
    total = 0.0

    for from_index, to_index in zip(order, order[1:]):
        value = matrix[from_index][to_index]
        if value is None:
            raise UnreachableRouteError("Route between some points is not available")
        if value < 0:
            raise InvalidMatrixError("OSRM returned invalid route matrix")
        total += float(value)

    return total


def nearest_neighbor_order(matrix: list[list[float | None]], points_count: int) -> list[int]:
    if points_count < 2:
        raise RouteOptimizationError("At least start and end points are required")

    end_index = points_count - 1
    current_index = 0
    unvisited = set(range(1, end_index))
    order = [0]

    while unvisited:
        next_index = min(
            unvisited,
            key=lambda candidate: (_matrix_value(matrix, current_index, candidate), candidate),
        )
        order.append(next_index)
        unvisited.remove(next_index)
        current_index = next_index

    order.append(end_index)
    return order


def two_opt_improve(
    order: list[int],
    matrix: list[list[float | None]],
    *,
    max_iterations: int = TWO_OPT_MAX_ITERATIONS,
) -> list[int]:
    if len(order) <= 3:
        return order[:]

    best_order = order[:]
    best_cost = calculate_route_cost(best_order, matrix)

    for _ in range(max_iterations):
        improved = False

        for start in range(1, len(best_order) - 2):
            for end in range(start + 1, len(best_order) - 1):
                candidate = (
                    best_order[:start]
                    + list(reversed(best_order[start : end + 1]))
                    + best_order[end + 1 :]
                )
                candidate_cost = calculate_route_cost(candidate, matrix)

                if candidate_cost < best_cost - IMPROVEMENT_TOLERANCE:
                    best_order = candidate
                    best_cost = candidate_cost
                    improved = True
                    break

            if improved:
                break

        if not improved:
            break

    return best_order


def optimize_order(
    durations: list[list[float | None]],
    distances: list[list[float | None]],
    optimization_metric: OptimizationMetric,
) -> tuple[list[int], list[int]]:
    selected_matrix = durations if optimization_metric == "duration" else distances
    points_count = len(selected_matrix)

    initial_order = nearest_neighbor_order(selected_matrix, points_count)
    optimized_order = two_opt_improve(initial_order, selected_matrix)

    return initial_order, optimized_order


async def build_optimized_route(
    payload: OptimizeRouteRequest,
    *,
    osrm_client: OsrmClient | None = None,
) -> OptimizeRouteResponse:
    if len(payload.points) > MAX_INTERMEDIATE_POINTS:
        raise TooManyPointsError("Too many points for MVP optimization")

    all_points = _build_points(payload)
    table_points = [
        CoordinateInput(
            latitude=point.latitude,
            longitude=point.longitude,
            label=point.label,
        )
        for point in all_points
    ]

    client = osrm_client or OsrmClient()
    table = await client.get_table(table_points, max_points=MAX_TOTAL_POINTS)
    durations = table.get("durations")
    distances = table.get("distances")

    validate_matrices(durations, distances, len(all_points))

    initial_order, optimized_order = optimize_order(
        durations,
        distances,
        payload.optimization_metric,
    )

    initial_duration_s = calculate_route_cost(initial_order, durations)
    optimized_duration_s = calculate_route_cost(optimized_order, durations)
    total_distance_m = calculate_route_cost(optimized_order, distances)
    total_duration_s = optimized_duration_s

    improvement_duration_s = max(0.0, initial_duration_s - optimized_duration_s)
    improvement_percent = (
        improvement_duration_s / initial_duration_s * 100.0
        if initial_duration_s > 0
        else 0.0
    )

    return OptimizeRouteResponse(
        status="completed",
        optimization_metric=payload.optimization_metric,
        points_count=len(all_points),
        total_distance_m=_round(total_distance_m),
        total_duration_s=_round(total_duration_s),
        initial_duration_s=_round(initial_duration_s),
        optimized_duration_s=_round(optimized_duration_s),
        improvement_duration_s=_round(improvement_duration_s),
        improvement_percent=_round(improvement_percent),
        ordered_points=_ordered_points(all_points, optimized_order),
        legs=_legs(optimized_order, durations, distances),
    )


def _build_points(payload: OptimizeRouteRequest) -> list[OptimizationPoint]:
    points: list[OptimizationPoint] = [
        OptimizationPoint(
            latitude=payload.start.latitude,
            longitude=payload.start.longitude,
            label=payload.start.label,
            type="start",
            original_index=0,
        )
    ]

    for index, point in enumerate(payload.points, start=1):
        points.append(
            OptimizationPoint(
                latitude=point.latitude,
                longitude=point.longitude,
                label=point.label,
                type="waypoint",
                original_index=index,
            )
        )

    points.append(
        OptimizationPoint(
            latitude=payload.end.latitude,
            longitude=payload.end.longitude,
            label=payload.end.label,
            type="end",
            original_index=len(payload.points) + 1,
        )
    )

    return points


def _ordered_points(
    all_points: list[OptimizationPoint],
    order: list[int],
) -> list[OrderedRoutePoint]:
    return [
        OrderedRoutePoint(
            order=position,
            type=all_points[point_index].type,
            label=all_points[point_index].label,
            latitude=all_points[point_index].latitude,
            longitude=all_points[point_index].longitude,
            original_index=all_points[point_index].original_index,
        )
        for position, point_index in enumerate(order)
    ]


def _legs(
    order: list[int],
    durations: list[list[float | None]],
    distances: list[list[float | None]],
) -> list[OptimizedRouteLeg]:
    return [
        OptimizedRouteLeg(
            from_order=position,
            to_order=position + 1,
            distance_m=_round(_matrix_value(distances, from_index, to_index)),
            duration_s=_round(_matrix_value(durations, from_index, to_index)),
        )
        for position, (from_index, to_index) in enumerate(zip(order, order[1:]))
    ]


def _matrix_value(
    matrix: list[list[float | None]],
    from_index: int,
    to_index: int,
) -> float:
    value = matrix[from_index][to_index]
    if value is None:
        raise UnreachableRouteError("Route between some points is not available")
    return float(value)


def _round(value: float) -> float:
    return round(float(value), 2)
