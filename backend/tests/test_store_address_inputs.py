import unittest

from app.schemas.optimization import CoordinateInput, OptimizeRouteRequest
from app.services.route_optimizer import build_optimized_route
from app.utils.address_normalizer import normalize_address


class FakeOsrmClient:
    def __init__(self) -> None:
        self.calls = []

    async def get_table(self, points, *, max_points):
        self.calls.append((points, max_points))
        return {
            "code": "Ok",
            "durations": [
                [0, 1, 1, 10],
                [1, 0, 0, 2],
                [1, 0, 0, 2],
                [10, 2, 2, 0],
            ],
            "distances": [
                [0, 100, 100, 1000],
                [100, 0, 0, 200],
                [100, 0, 0, 200],
                [1000, 200, 200, 0],
            ],
            "sources": [],
            "destinations": [],
        }


class StoreAddressInputTests(unittest.IsolatedAsyncioTestCase):
    def test_extracts_store_names_that_contain_address_marker_substrings(self):
        semishagoff = normalize_address(
            "\u0421\u0435\u043c\u0438\u0448\u0430\u0433\u043e\u0444\u0444"
            " \u2014 "
            "\u041a\u043e\u0440\u0430\u0431\u043b\u0435\u0441\u0442\u0440\u043e"
            "\u0438\u0442\u0435\u043b\u0435\u0439 \u0443\u043b, 16"
        )
        perekrestok = normalize_address(
            "\u041f\u0435\u0440\u0435\u043a\u0440\u0435\u0441\u0442\u043e\u043a"
            " \u0422\u0414 \u2014 "
            "\u041d\u0430\u043b\u0438\u0447\u043d\u0430\u044f \u0443\u043b, 44"
        )

        self.assertEqual(
            semishagoff.place_name,
            "\u0421\u0435\u043c\u0438\u0448\u0430\u0433\u043e\u0444\u0444",
        )
        self.assertEqual(
            semishagoff.address_for_geocoding,
            "\u041a\u043e\u0440\u0430\u0431\u043b\u0435\u0441\u0442\u0440\u043e"
            "\u0438\u0442\u0435\u043b\u0435\u0439 \u0443\u043b, 16",
        )
        self.assertEqual(
            perekrestok.place_name,
            "\u041f\u0435\u0440\u0435\u043a\u0440\u0435\u0441\u0442\u043e\u043a \u0422\u0414",
        )
        self.assertEqual(
            perekrestok.address_for_geocoding,
            "\u041d\u0430\u043b\u0438\u0447\u043d\u0430\u044f \u0443\u043b, 44",
        )

    def test_line_address_is_not_treated_as_place_name(self):
        result = normalize_address(
            "19-\u044f \u043b\u0438\u043d\u0438\u044f \u0412.\u041e., 14/54"
        )

        self.assertIsNone(result.place_name)
        self.assertEqual(
            result.address_for_geocoding,
            "19-\u044f \u043b\u0438\u043d\u0438\u044f \u0412.\u041e., 14/54",
        )

    def test_normalizes_abbreviations_from_route_list(self):
        avenue = normalize_address(
            "\u0421\u0435\u043c\u0438\u0448\u0430\u0433\u043e\u0444\u0444"
            " \u2014 \u041a\u0418\u041c\u0430 \u043f\u0440, 4"
        )
        boulevard = normalize_address(
            "\u0421\u0435\u043c\u0438\u0448\u0430\u0433\u043e\u0444\u0444"
            " \u2014 "
            "\u0412\u0438\u043b\u044c\u043a\u0438\u0446\u043a\u0438\u0439"
            " \u0431-\u0440, 4"
        )
        vo_avenue = normalize_address(
            "\u0421\u0435\u043c\u0438\u0448\u0430\u0433\u043e\u0444\u0444"
            " \u2014 "
            "\u0421\u0440\u0435\u0434\u043d\u0438\u0439"
            " \u043f\u0440, \u0412.\u041e., 61"
        )
        island = normalize_address(
            "\u041a\u0430\u043d\u043e\u043d\u0435\u0440\u0441\u043a\u0438"
            "\u0439 \u043e\u0441\u0442\u0440\u043e\u0432, 22"
        )

        self.assertIn("\u043f\u0440\u043e\u0441\u043f\u0435\u043a\u0442", avenue.tokens)
        self.assertIn("\u0431\u0443\u043b\u044c\u0432\u0430\u0440", boulevard.tokens)
        self.assertIn("\u043f\u0440\u043e\u0441\u043f\u0435\u043a\u0442", vo_avenue.tokens)
        self.assertIn("\u0432\u0430\u0441\u0438\u043b\u044c\u0435\u0432\u0441\u043a\u0438\u0439", vo_avenue.tokens)
        self.assertIsNone(island.place_name)
        self.assertEqual(
            island.address_for_geocoding,
            "\u041a\u0430\u043d\u043e\u043d\u0435\u0440\u0441\u043a\u0438"
            "\u0439 \u043e\u0441\u0442\u0440\u043e\u0432, 22",
        )

    async def test_optimizer_keeps_duplicate_coordinates_as_separate_stores(self):
        client = FakeOsrmClient()
        same_latitude = 59.950368
        same_longitude = 30.236862
        payload = OptimizeRouteRequest(
            start=CoordinateInput(latitude=59.9398, longitude=30.3141, label="Start"),
            end=CoordinateInput(latitude=59.9297, longitude=30.3627, label="End"),
            points=[
                CoordinateInput(
                    latitude=same_latitude,
                    longitude=same_longitude,
                    label=(
                        "\u0421\u0435\u043c\u0438\u0448\u0430\u0433\u043e\u0444\u0444"
                        " \u2014 "
                        "\u041a\u043e\u0440\u0430\u0431\u043b\u0435"
                        "\u0441\u0442\u0440\u043e\u0438\u0442\u0435\u043b\u0435"
                        "\u0439 \u0443\u043b, 36"
                    ),
                ),
                CoordinateInput(
                    latitude=same_latitude,
                    longitude=same_longitude,
                    label=(
                        "\u0410\u0433\u0440\u043e\u0442\u043e\u0440\u0433 6607"
                        " \u2014 "
                        "\u041a\u043e\u0440\u0430\u0431\u043b\u0435"
                        "\u0441\u0442\u0440\u043e\u0438\u0442\u0435\u043b\u0435"
                        "\u0439 \u0443\u043b, 36"
                    ),
                ),
            ],
        )

        result = await build_optimized_route(payload, osrm_client=client)

        waypoint_labels = [
            point.label for point in result.ordered_points if point.type == "waypoint"
        ]
        self.assertEqual(result.points_count, 4)
        self.assertEqual(len(waypoint_labels), 2)
        self.assertNotEqual(waypoint_labels[0], waypoint_labels[1])
        self.assertEqual(
            [(point.latitude, point.longitude) for point in result.ordered_points],
            [
                (59.9398, 30.3141),
                (same_latitude, same_longitude),
                (same_latitude, same_longitude),
                (59.9297, 30.3627),
            ],
        )


if __name__ == "__main__":
    unittest.main()
