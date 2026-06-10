import unittest

from app.schemas.optimization import CoordinateInput, OptimizeRouteRequest
from app.services.route_optimizer import (
    MAX_TOTAL_POINTS,
    TooManyPointsError,
    UnreachableRouteError,
    build_optimized_route,
    calculate_route_cost,
    nearest_neighbor_order,
    two_opt_improve,
    validate_matrix,
)


class FakeOsrmClient:
    def __init__(self, *, durations, distances):
        self.durations = durations
        self.distances = distances
        self.calls = []

    async def get_table(self, points, *, max_points):
        self.calls.append((points, max_points))
        return {
            "code": "Ok",
            "durations": self.durations,
            "distances": self.distances,
            "sources": [],
            "destinations": [],
        }


class RouteOptimizerTests(unittest.IsolatedAsyncioTestCase):
    def test_calculate_route_cost_uses_directed_matrix(self):
        matrix = [
            [0, 1, 10],
            [5, 0, 2],
            [3, 7, 0],
        ]

        self.assertEqual(calculate_route_cost([0, 1, 2], matrix), 3)
        self.assertEqual(calculate_route_cost([2, 1, 0], matrix), 12)

    def test_two_opt_recalculates_full_asymmetric_route_cost(self):
        matrix = [
            [0, 1, 2, 999],
            [999, 0, 100, 1],
            [999, 1, 0, 100],
            [999, 999, 999, 0],
        ]

        initial_order = nearest_neighbor_order(matrix, 4)
        optimized_order = two_opt_improve(initial_order, matrix)

        self.assertEqual(initial_order, [0, 1, 2, 3])
        self.assertEqual(optimized_order, [0, 2, 1, 3])
        self.assertLess(
            calculate_route_cost(optimized_order, matrix),
            calculate_route_cost(initial_order, matrix),
        )

    def test_validate_matrix_rejects_null_cells(self):
        matrix = [
            [0, None],
            [10, 0],
        ]

        with self.assertRaisesRegex(UnreachableRouteError, "unreachable"):
            validate_matrix(matrix, 2, "duration")

    async def test_build_optimized_route_without_intermediate_points(self):
        client = FakeOsrmClient(
            durations=[
                [0, 10],
                [11, 0],
            ],
            distances=[
                [0, 1000],
                [1100, 0],
            ],
        )
        payload = OptimizeRouteRequest(
            start=CoordinateInput(latitude=59.9398, longitude=30.3141, label="Start"),
            end=CoordinateInput(latitude=59.9297, longitude=30.3627, label="End"),
            points=[],
        )

        result = await build_optimized_route(payload, osrm_client=client)

        self.assertEqual(client.calls[0][1], MAX_TOTAL_POINTS)
        self.assertEqual(result.points_count, 2)
        self.assertEqual([point.type for point in result.ordered_points], ["start", "end"])
        self.assertEqual([point.original_index for point in result.ordered_points], [0, 1])
        self.assertEqual(result.total_duration_s, 10)
        self.assertEqual(result.total_distance_m, 1000)
        self.assertEqual(len(result.legs), 1)

    async def test_build_optimized_route_keeps_start_end_fixed_and_all_waypoints_once(self):
        client = FakeOsrmClient(
            durations=[
                [0, 1, 2, 999],
                [999, 0, 100, 1],
                [999, 1, 0, 100],
                [999, 999, 999, 0],
            ],
            distances=[
                [0, 10, 20, 9990],
                [9990, 0, 1000, 10],
                [9990, 10, 0, 1000],
                [9990, 9990, 9990, 0],
            ],
        )
        payload = OptimizeRouteRequest(
            start=CoordinateInput(latitude=59.9398, longitude=30.3141, label="Start"),
            end=CoordinateInput(latitude=59.9297, longitude=30.3627, label="End"),
            points=[
                CoordinateInput(latitude=59.9488, longitude=30.3359, label="A"),
                CoordinateInput(latitude=59.9663, longitude=30.3116, label="B"),
            ],
        )

        result = await build_optimized_route(payload, osrm_client=client)
        original_indexes = [point.original_index for point in result.ordered_points]

        self.assertEqual(original_indexes, [0, 2, 1, 3])
        self.assertEqual(result.ordered_points[0].type, "start")
        self.assertEqual(result.ordered_points[-1].type, "end")
        self.assertEqual(sorted(original_indexes), [0, 1, 2, 3])
        self.assertEqual(result.initial_duration_s, 201)
        self.assertEqual(result.optimized_duration_s, 4)
        self.assertEqual(result.improvement_duration_s, 197)
        self.assertGreater(result.improvement_percent, 0)

    async def test_build_optimized_route_rejects_too_many_intermediate_points(self):
        payload = OptimizeRouteRequest(
            start=CoordinateInput(latitude=59.9398, longitude=30.3141),
            end=CoordinateInput(latitude=59.9297, longitude=30.3627),
            points=[
                CoordinateInput(latitude=59.9, longitude=30.3)
                for _ in range(101)
            ],
        )

        with self.assertRaisesRegex(TooManyPointsError, "Too many points"):
            await build_optimized_route(payload, osrm_client=FakeOsrmClient(
                durations=[],
                distances=[],
            ))


if __name__ == "__main__":
    unittest.main()
