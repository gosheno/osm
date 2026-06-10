import unittest

from app.clients.osrm_client import (
    MAX_OSRM_POINTS,
    OsrmClient,
    format_coordinates_for_osrm,
    format_osrm_radiuses,
    validate_points,
)


class FakeOsrmClient(OsrmClient):
    def __init__(self, response):
        self.base_url = "http://osrm:5000"
        self.response = response
        self.calls = []

    async def _get(self, path, *, params):
        self.calls.append((path, params))
        return self.response


class OsrmClientTests(unittest.IsolatedAsyncioTestCase):
    def test_format_coordinates_for_osrm_uses_lon_lat_order(self):
        result = format_coordinates_for_osrm(
            [
                {"latitude": 59.9398, "longitude": 30.3141},
                {"latitude": 59.9297, "longitude": 30.3627},
            ]
        )

        self.assertEqual(result, "30.3141,59.9398;30.3627,59.9297")

    def test_format_osrm_radiuses_matches_points_count(self):
        result = format_osrm_radiuses(
            [
                {"latitude": 59.9398, "longitude": 30.3141},
                {"latitude": 59.9297, "longitude": 30.3627},
                {"latitude": 59.9488, "longitude": 30.3359},
            ]
        )

        self.assertEqual(result, "1000;1000;1000")

    def test_validate_points_rejects_too_many_points(self):
        points = [
            {"latitude": 59.9, "longitude": 30.3}
            for _ in range(MAX_OSRM_POINTS + 1)
        ]

        with self.assertRaisesRegex(ValueError, "At most 100 points"):
            validate_points(points)

    async def test_get_route_returns_normalized_route_json(self):
        client = FakeOsrmClient(
            {
                "code": "Ok",
                "routes": [
                    {
                        "distance": 3830.9,
                        "duration": 379.6,
                        "geometry": {
                            "type": "LineString",
                            "coordinates": [[30.314729, 59.939376]],
                        },
                    }
                ],
                "waypoints": [
                    {
                        "location": [30.314729, 59.939376],
                        "name": "Невский проспект",
                        "distance": 12.3,
                    }
                ],
            }
        )

        result = await client.get_route(
            [
                {"latitude": 59.9398, "longitude": 30.3141},
                {"latitude": 59.9297, "longitude": 30.3627},
            ]
        )

        self.assertEqual(
            client.calls[0][0],
            "/route/v1/driving/30.3141,59.9398;30.3627,59.9297",
        )
        self.assertEqual(client.calls[0][1]["geometries"], "geojson")
        self.assertEqual(client.calls[0][1]["radiuses"], "1000;1000")
        self.assertEqual(result["code"], "Ok")
        self.assertEqual(result["distance_m"], 3830.9)
        self.assertEqual(result["duration_s"], 379.6)
        self.assertEqual(result["geometry"]["type"], "LineString")
        self.assertEqual(result["waypoints"][0]["latitude"], 59.939376)
        self.assertEqual(result["waypoints"][0]["longitude"], 30.314729)

    async def test_get_table_returns_duration_and_distance_matrices(self):
        client = FakeOsrmClient(
            {
                "code": "Ok",
                "durations": [[0, 379.6], [379.0, 0]],
                "distances": [[0, 3842.6], [3752.7, 0]],
                "sources": [{"location": [30.3141, 59.9398], "name": ""}],
                "destinations": [{"location": [30.3627, 59.9297], "name": ""}],
            }
        )

        result = await client.get_table(
            [
                {"latitude": 59.9398, "longitude": 30.3141},
                {"latitude": 59.9297, "longitude": 30.3627},
            ]
        )

        self.assertEqual(
            client.calls[0][0],
            "/table/v1/driving/30.3141,59.9398;30.3627,59.9297",
        )
        self.assertEqual(client.calls[0][1]["annotations"], "duration,distance")
        self.assertEqual(client.calls[0][1]["radiuses"], "1000;1000")
        self.assertEqual(result["code"], "Ok")
        self.assertEqual(result["durations"], [[0.0, 379.6], [379.0, 0.0]])
        self.assertEqual(result["distances"], [[0.0, 3842.6], [3752.7, 0.0]])
        self.assertEqual(result["sources"][0]["latitude"], 59.9398)
        self.assertEqual(result["destinations"][0]["longitude"], 30.3627)


if __name__ == "__main__":
    unittest.main()
