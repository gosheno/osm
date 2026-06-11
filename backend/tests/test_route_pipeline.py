import unittest

from app.core.exceptions import AppError
from app.schemas.route import OptimizeRouteByAddressesRequest
from app.services.route_pipeline import optimize_route_by_addresses


class FakeAddressService:
    def __init__(self, results):
        self.results = results
        self.calls = []

    async def geocode_address(
        self,
        address,
        default_city="санкт-петербург",
        place_name=None,
        force_refresh=False,
    ):
        self.calls.append(
            {
                "address": address,
                "default_city": default_city,
                "place_name": place_name,
                "force_refresh": force_refresh,
            }
        )
        return self.results[address]


class FakeOsrmClient:
    def __init__(self):
        self.calls = []

    async def get_table(self, points, *, max_points):
        self.calls.append((points, max_points))
        return {
            "code": "Ok",
            "durations": [
                [0, 1, 2, 10],
                [1, 0, 1, 10],
                [2, 1, 0, 1],
                [10, 10, 1, 0],
            ],
            "distances": [
                [0, 100, 200, 1000],
                [100, 0, 100, 1000],
                [200, 100, 0, 100],
                [1000, 1000, 100, 0],
            ],
            "sources": [],
            "destinations": [],
        }


def geocoded(
    address,
    *,
    latitude,
    longitude,
    original_address=None,
    place_name=None,
    source="nominatim",
    status="found",
    error=None,
):
    return {
        "id": 1,
        "original_address": original_address or address,
        "address_for_geocoding": original_address or address,
        "normalized_address": f"normalized {original_address or address}",
        "place_name": place_name,
        "latitude": latitude,
        "longitude": longitude,
        "geocoding_status": status,
        "geocoding_provider": "nominatim",
        "confidence_score": 80.0 if latitude is not None else None,
        "source": source,
        "display_name": None,
        "error": error,
    }


class RoutePipelineTests(unittest.IsolatedAsyncioTestCase):
    async def test_builds_full_route_response_with_batches_and_yandex_links(self):
        store_a = (
            "\u0421\u0435\u043c\u0438\u0448\u0430\u0433\u043e\u0444\u0444"
            " \u2014 "
            "\u041a\u043e\u0440\u0430\u0431\u043b\u0435"
            "\u0441\u0442\u0440\u043e\u0438\u0442\u0435\u043b\u0435"
            "\u0439 \u0443\u043b, 36"
        )
        store_b = (
            "\u0410\u0433\u0440\u043e\u0442\u043e\u0440\u0433 6607"
            " \u2014 "
            "\u041a\u043e\u0440\u0430\u0431\u043b\u0435"
            "\u0441\u0442\u0440\u043e\u0438\u0442\u0435\u043b\u0435"
            "\u0439 \u0443\u043b, 36"
        )
        start = "\u041b\u0438\u0433\u043e\u0432\u043e"
        end = "\u041b\u0438\u0433\u043e\u0432\u043e"
        same_latitude = 59.950368
        same_longitude = 30.236862
        service = FakeAddressService(
            {
                start: geocoded(start, latitude=59.8314, longitude=30.1768),
                end: geocoded(end, latitude=59.8314, longitude=30.1768),
                store_a: geocoded(
                    store_a,
                    latitude=same_latitude,
                    longitude=same_longitude,
                    original_address=(
                        "\u041a\u043e\u0440\u0430\u0431\u043b\u0435"
                        "\u0441\u0442\u0440\u043e\u0438\u0442\u0435\u043b\u0435"
                        "\u0439 \u0443\u043b, 36"
                    ),
                    place_name=(
                        "\u0421\u0435\u043c\u0438\u0448\u0430\u0433\u043e\u0444\u0444"
                    ),
                ),
                store_b: geocoded(
                    store_b,
                    latitude=same_latitude,
                    longitude=same_longitude,
                    original_address=(
                        "\u041a\u043e\u0440\u0430\u0431\u043b\u0435"
                        "\u0441\u0442\u0440\u043e\u0438\u0442\u0435\u043b\u0435"
                        "\u0439 \u0443\u043b, 36"
                    ),
                    place_name="\u0410\u0433\u0440\u043e\u0442\u043e\u0440\u0433 6607",
                    source="database",
                ),
            }
        )
        osrm_client = FakeOsrmClient()

        result = await optimize_route_by_addresses(
            OptimizeRouteByAddressesRequest(
                start_address=start,
                end_address=end,
                addresses=[store_a, store_b],
                batch_size=1,
            ),
            db=None,
            address_service_factory=lambda db: service,
            osrm_client=osrm_client,
        )

        labels = [point.label for point in result.ordered_points]
        waypoint_coords = [
            (point.latitude, point.longitude)
            for point in result.ordered_points
            if point.type == "waypoint"
        ]

        self.assertEqual(result.status, "completed")
        self.assertEqual(result.total_input_addresses, 2)
        self.assertEqual(result.total_points, 4)
        self.assertEqual(result.failed_addresses, [])
        self.assertEqual(labels, [start, store_a, store_b, end])
        self.assertEqual(
            waypoint_coords,
            [(same_latitude, same_longitude), (same_latitude, same_longitude)],
        )
        self.assertEqual(result.batches[0].points_count, 2)
        self.assertEqual(result.batches[1].points_count, 3)
        self.assertEqual(result.ordered_points[1].district, "Василеостровский")
        self.assertEqual(result.batches[0].district, "Василеостровский")
        self.assertEqual(result.batches[0].districts, ["Василеостровский"])
        self.assertEqual(result.batches[0].points[1].district, "Василеостровский")
        self.assertTrue(result.batches[0].yandex_maps_url.startswith("https://yandex.ru/maps/2/"))
        self.assertEqual(len(osrm_client.calls), 1)
        self.assertTrue(result.geocoded_addresses[2].from_cache)

    async def test_returns_failed_response_when_any_address_is_not_geocoded(self):
        start = "Start"
        end = "End"
        missing = "Missing"
        service = FakeAddressService(
            {
                start: geocoded(start, latitude=59.8, longitude=30.1),
                end: geocoded(end, latitude=59.9, longitude=30.2),
                missing: geocoded(
                    missing,
                    latitude=None,
                    longitude=None,
                    status="not_found",
                    error="Address was not found",
                ),
            }
        )
        osrm_client = FakeOsrmClient()

        with self.assertRaises(AppError) as context:
            await optimize_route_by_addresses(
                OptimizeRouteByAddressesRequest(
                    start_address=start,
                    end_address=end,
                    addresses=[missing],
                ),
                db=None,
                address_service_factory=lambda db: service,
                osrm_client=osrm_client,
            )

        self.assertEqual(context.exception.code, "WAYPOINT_ADDRESS_NOT_FOUND")
        self.assertEqual(len(context.exception.failed_addresses), 1)
        self.assertEqual(context.exception.failed_addresses[0]["input_address"], missing)
        self.assertEqual(osrm_client.calls, [])

    async def test_error_geocoding_address_includes_provider_and_source(self):
        start = "Start"
        end = "End"

        class ErrorAddressService(FakeAddressService):
            async def geocode_address(self, address, **kwargs):
                if address == start:
                    return geocoded(start, latitude=59.8, longitude=30.1)
                if address == end:
                    return geocoded(end, latitude=59.9, longitude=30.2)
                raise Exception("Geocoder failure")

        service = ErrorAddressService({})
        osrm_client = FakeOsrmClient()

        with self.assertRaises(AppError) as context:
            await optimize_route_by_addresses(
                OptimizeRouteByAddressesRequest(
                    start_address=start,
                    end_address=end,
                    addresses=["Broken"],
                ),
                db=None,
                address_service_factory=lambda db: service,
                osrm_client=osrm_client,
            )

        self.assertEqual(context.exception.code, "WAYPOINT_ADDRESS_NOT_FOUND")
        self.assertEqual(len(context.exception.failed_addresses), 1)
        failed = context.exception.failed_addresses[0]
        self.assertEqual(failed["input_address"], "Broken")
        self.assertEqual(failed["geocoding_provider"], "nominatim")
        self.assertEqual(failed["source"], "nominatim")
        self.assertEqual(osrm_client.calls, [])


if __name__ == "__main__":
    unittest.main()
