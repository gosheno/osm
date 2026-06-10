import unittest

from app.schemas.batching import BatchPointInput, BatchRouteRequest, RouteLegInput
from app.services.route_batching import (
    InvalidBatchSizeError,
    InvalidLegsError,
    InvalidOrderedPointsError,
    batch_optimized_route,
)


def make_points(waypoints_count: int) -> list[BatchPointInput]:
    points = [
        BatchPointInput(
            order=0,
            type="start",
            label="Start",
            latitude=59.9,
            longitude=30.3,
            original_index=0,
        )
    ]

    for index in range(1, waypoints_count + 1):
        points.append(
            BatchPointInput(
                order=index,
                type="waypoint",
                label=f"Point {index}",
                latitude=59.9 + index * 0.001,
                longitude=30.3 + index * 0.001,
                original_index=index,
            )
        )

    end_order = waypoints_count + 1
    points.append(
        BatchPointInput(
            order=end_order,
            type="end",
            label="End",
            latitude=59.8,
            longitude=30.4,
            original_index=end_order,
        )
    )

    return points


def make_legs(points: list[BatchPointInput]) -> list[RouteLegInput]:
    return [
        RouteLegInput(
            from_order=from_point.order,
            to_order=to_point.order,
            distance_m=(from_point.order + 1) * 100,
            duration_s=(from_point.order + 1) * 10,
        )
        for from_point, to_point in zip(points, points[1:])
    ]


def global_orders(batch) -> list[int]:
    return [point.global_order for point in batch.points]


class RouteBatchingTests(unittest.TestCase):
    def test_start_and_end_only_creates_single_batch(self):
        points = make_points(0)
        result = batch_optimized_route(
            BatchRouteRequest(
                ordered_points=points,
                legs=make_legs(points),
                batch_size=15,
            )
        )

        self.assertEqual(result.batches_count, 1)
        self.assertEqual(global_orders(result.batches[0]), [0, 1])
        self.assertEqual(result.batches[0].points_count, 2)
        self.assertEqual(result.batches[0].distance_m, 100)
        self.assertEqual(result.batches[0].duration_s, 10)

    def test_one_waypoint_creates_single_batch(self):
        points = make_points(1)
        result = batch_optimized_route(
            BatchRouteRequest(
                ordered_points=points,
                legs=make_legs(points),
                batch_size=15,
            )
        )

        self.assertEqual(result.batches_count, 1)
        self.assertEqual(global_orders(result.batches[0]), [0, 1, 2])
        self.assertEqual(result.batches[0].distance_m, 300)
        self.assertEqual(result.batches[0].duration_s, 30)

    def test_three_waypoints_with_batch_size_two_uses_transition_point(self):
        points = make_points(3)
        result = batch_optimized_route(
            BatchRouteRequest(
                ordered_points=points,
                legs=make_legs(points),
                batch_size=2,
            )
        )

        self.assertEqual(result.batches_count, 2)
        self.assertEqual(global_orders(result.batches[0]), [0, 1, 2])
        self.assertEqual(global_orders(result.batches[1]), [2, 3, 4])
        self.assertFalse(result.batches[0].points[-1].is_transition_point)
        self.assertTrue(result.batches[1].points[0].is_transition_point)
        self.assertEqual(result.batches[0].distance_m, 300)
        self.assertEqual(result.batches[1].distance_m, 700)

    def test_fifteen_waypoints_with_batch_size_fifteen_creates_one_batch(self):
        result = batch_optimized_route(
            BatchRouteRequest(ordered_points=make_points(15), batch_size=15)
        )

        self.assertEqual(result.batches_count, 1)
        self.assertEqual(result.batches[0].points_count, 17)
        self.assertEqual(global_orders(result.batches[0]), list(range(17)))

    def test_sixteen_waypoints_with_batch_size_fifteen_creates_two_batches(self):
        result = batch_optimized_route(
            BatchRouteRequest(ordered_points=make_points(16), batch_size=15)
        )

        self.assertEqual(result.batches_count, 2)
        self.assertEqual(result.batches[0].points_count, 16)
        self.assertEqual(global_orders(result.batches[0]), list(range(16)))
        self.assertEqual(global_orders(result.batches[1]), [15, 16, 17])
        self.assertTrue(result.batches[1].points[0].is_transition_point)

    def test_thirty_waypoints_with_batch_size_fifteen_creates_two_batches(self):
        result = batch_optimized_route(
            BatchRouteRequest(ordered_points=make_points(30), batch_size=15)
        )

        self.assertEqual(result.batches_count, 2)
        self.assertEqual(result.batches[0].points_count, 16)
        self.assertEqual(result.batches[1].points_count, 17)
        self.assertEqual(global_orders(result.batches[0]), list(range(16)))
        self.assertEqual(global_orders(result.batches[1]), [15] + list(range(16, 32)))

    def test_thirty_one_waypoints_with_batch_size_fifteen_creates_three_batches(self):
        result = batch_optimized_route(
            BatchRouteRequest(ordered_points=make_points(31), batch_size=15)
        )

        self.assertEqual(result.batches_count, 3)
        self.assertEqual(result.batches[0].points_count, 16)
        self.assertEqual(result.batches[1].points_count, 16)
        self.assertEqual(result.batches[2].points_count, 3)
        self.assertEqual(global_orders(result.batches[2]), [30, 31, 32])
        self.assertTrue(result.batches[1].points[0].is_transition_point)
        self.assertTrue(result.batches[2].points[0].is_transition_point)

    def test_without_legs_returns_null_totals(self):
        result = batch_optimized_route(
            BatchRouteRequest(ordered_points=make_points(3), legs=None, batch_size=2)
        )

        self.assertIsNone(result.batches[0].distance_m)
        self.assertIsNone(result.batches[0].duration_s)

    def test_include_transition_point_false_does_not_repeat_previous_batch_end(self):
        result = batch_optimized_route(
            BatchRouteRequest(
                ordered_points=make_points(3),
                batch_size=2,
                include_transition_point=False,
            )
        )

        self.assertEqual(global_orders(result.batches[0]), [0, 1, 2])
        self.assertEqual(global_orders(result.batches[1]), [3, 4])
        self.assertFalse(result.batches[1].points[0].is_transition_point)

    def test_unsorted_points_are_sorted_by_order(self):
        points = make_points(2)
        result = batch_optimized_route(
            BatchRouteRequest(
                ordered_points=[points[2], points[0], points[3], points[1]],
                legs=make_legs(points),
                batch_size=15,
            )
        )

        self.assertEqual(global_orders(result.batches[0]), [0, 1, 2, 3])

    def test_rejects_invalid_batch_size(self):
        with self.assertRaisesRegex(InvalidBatchSizeError, "between 1 and 20"):
            batch_optimized_route(
                BatchRouteRequest(ordered_points=make_points(2), batch_size=21)
            )

    def test_rejects_duplicate_order_values(self):
        points = make_points(2)
        points[2] = points[2].model_copy(update={"order": 1})

        with self.assertRaisesRegex(InvalidOrderedPointsError, "duplicate order"):
            batch_optimized_route(
                BatchRouteRequest(ordered_points=points, batch_size=15)
            )

    def test_rejects_missing_start_or_end(self):
        points = make_points(1)
        points[0] = points[0].model_copy(update={"type": "waypoint"})

        with self.assertRaisesRegex(InvalidOrderedPointsError, "First point"):
            batch_optimized_route(
                BatchRouteRequest(ordered_points=points, batch_size=15)
            )

    def test_rejects_start_or_end_in_middle(self):
        points = make_points(2)
        points[1] = points[1].model_copy(update={"type": "end"})

        with self.assertRaisesRegex(InvalidOrderedPointsError, "End point"):
            batch_optimized_route(
                BatchRouteRequest(ordered_points=points, batch_size=15)
            )

    def test_rejects_legs_that_do_not_match_ordered_points(self):
        points = make_points(2)
        legs = make_legs(points)
        legs[0] = legs[0].model_copy(update={"to_order": 99})

        with self.assertRaisesRegex(InvalidLegsError, "legs do not match"):
            batch_optimized_route(
                BatchRouteRequest(
                    ordered_points=points,
                    legs=legs,
                    batch_size=15,
                )
            )


if __name__ == "__main__":
    unittest.main()
