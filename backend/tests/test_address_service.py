import unittest

from app.clients.nominatim_client import GeocodingCandidate
from app.services.address_service import AddressService


class FakeMappingResult:
    def __init__(self, row):
        self.row = row

    def mappings(self):
        return self

    def first(self):
        return self.row

    def one(self):
        return self.row


class FakeDb:
    def __init__(self, existing=None):
        self.existing = existing
        self.execute_calls = []
        self.commits = 0

    async def execute(self, statement, params):
        statement_text = str(statement)
        self.execute_calls.append((statement_text, params))

        if "SELECT" in statement_text and "FROM addresses" in statement_text:
            return FakeMappingResult(self.existing)

        if "SET last_used_at = now()" in statement_text:
            return FakeMappingResult(None)

        return FakeMappingResult(
            {
                "id": 1,
                "original_address": params["original_address"],
                "normalized_address": params["normalized_address"],
                "latitude": params.get("latitude"),
                "longitude": params.get("longitude"),
                "geocoding_status": params.get(
                    "geocoding_status",
                    "found" if params.get("latitude") is not None else "not_found",
                ),
                "geocoding_provider": params.get("geocoding_provider", "nominatim"),
                "confidence_score": params.get("confidence_score"),
            }
        )

    async def commit(self):
        self.commits += 1


class FakeGeocoder:
    def __init__(self, candidates):
        self.candidates = candidates
        self.queries = []

    async def search(self, query):
        self.queries.append(query)
        return self.candidates


class AddressServiceTests(unittest.IsolatedAsyncioTestCase):
    async def test_geocode_uses_first_nominatim_candidate(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder(
            [
                GeocodingCandidate(
                    latitude=59.936561,
                    longitude=30.315904,
                    display_name="Невский проспект, 9, Санкт-Петербург",
                    importance=0.74,
                )
            ]
        )

        result = await service.geocode_address("СПБ, Невский пр-т д. 9")

        self.assertEqual(
            service.geocoder.queries,
            ["санкт-петербург, невский проспект дом 9"],
        )
        self.assertEqual(result["latitude"], 59.936561)
        self.assertEqual(result["longitude"], 30.315904)
        self.assertEqual(result["geocoding_status"], "found")
        self.assertEqual(result["geocoding_provider"], "nominatim")
        self.assertEqual(result["confidence_score"], 74.0)
        self.assertEqual(result["source"], "nominatim")
        self.assertEqual(
            result["display_name"],
            "Невский проспект, 9, Санкт-Петербург",
        )
        self.assertIsNone(result["error"])

    async def test_geocode_uses_address_part_when_place_name_is_in_input(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder(
            [
                GeocodingCandidate(
                    latitude=59.936561,
                    longitude=30.315904,
                    display_name="Невский проспект, 9, Санкт-Петербург",
                    importance=0.74,
                )
            ]
        )

        result = await service.geocode_address("Пятёрочка, СПБ, Невский пр-т д. 9")

        self.assertEqual(result["place_name"], "Пятёрочка")
        self.assertEqual(result["original_address"], "Пятёрочка, СПБ, Невский пр-т д. 9")
        self.assertEqual(result["address_for_geocoding"], "СПБ, Невский пр-т д. 9")
        self.assertEqual(
            service.geocoder.queries,
            ["санкт-петербург, невский проспект дом 9"],
        )
        self.assertEqual(result["source"], "nominatim")
        self.assertEqual(db.execute_calls[1][1]["original_address"], "СПБ, Невский пр-т д. 9")

    async def test_geocode_keeps_explicit_place_name_when_result_is_cached(self):
        db = FakeDb(
            existing={
                "id": 6,
                "original_address": "СПБ, Невский пр-т д. 9",
                "normalized_address": "санкт-петербург, невский проспект дом 9",
                "latitude": 59.936561,
                "longitude": 30.315904,
                "geocoding_status": "found",
                "geocoding_provider": "nominatim",
                "confidence_score": 74.0,
            }
        )
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])

        result = await service.geocode_address(
            "СПБ, Невский пр-т д. 9",
            place_name="Магнит",
        )

        self.assertEqual(service.geocoder.queries, [])
        self.assertEqual(result["place_name"], "Магнит")
        self.assertEqual(result["source"], "database")
        self.assertEqual(result["address_for_geocoding"], "СПБ, Невский пр-т д. 9")

    async def test_geocode_handles_no_candidates_as_not_found(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])

        result = await service.geocode_address("СПБ, Невский пр-т д. 9")

        self.assertIsNone(result["latitude"])
        self.assertIsNone(result["longitude"])
        self.assertEqual(result["geocoding_status"], "not_found")
        self.assertEqual(result["geocoding_provider"], "nominatim")
        self.assertEqual(result["source"], "nominatim")
        self.assertEqual(result["error"], "Address was not found")

    async def test_geocode_returns_cached_not_found_from_database(self):
        db = FakeDb(
            existing={
                "id": 2,
                "original_address": "string",
                "normalized_address": "санкт-петербург, string",
                "latitude": None,
                "longitude": None,
                "geocoding_status": "not_found",
                "geocoding_provider": "nominatim",
                "confidence_score": None,
            }
        )
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])

        result = await service.geocode_address("string")

        self.assertEqual(service.geocoder.queries, [])
        self.assertEqual(result["id"], 2)
        self.assertEqual(result["geocoding_status"], "not_found")
        self.assertEqual(result["source"], "database")
        self.assertEqual(result["error"], "Address was not found")
        self.assertEqual(db.commits, 1)

    async def test_manual_geocoding_overrides_cached_not_found_demo_address(self):
        db = FakeDb(
            existing={
                "id": 3,
                "original_address": "Санкт-Петербург, 6-я линия В.О. 15",
                "normalized_address": "санкт-петербург, 6-я линия васильевского острова 15",
                "latitude": None,
                "longitude": None,
                "geocoding_status": "not_found",
                "geocoding_provider": "nominatim",
                "confidence_score": None,
            }
        )
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])

        result = await service.geocode_address("Санкт-Петербург, 6-я линия В.О. 15")

        self.assertEqual(service.geocoder.queries, [])
        self.assertEqual(result["geocoding_status"], "manual")
        self.assertEqual(result["geocoding_provider"], "manual")
        self.assertEqual(result["source"], "manual")
        self.assertEqual(result["latitude"], 59.9434)
        self.assertEqual(result["longitude"], 30.2787)
        self.assertIsNone(result["error"])

    async def test_manual_geocoding_supports_kirishi_test_set_address(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])

        result = await service.geocode_address(
            "Нефтехимиков 18А",
            default_city="Кириши, Ленинградская область",
        )

        self.assertEqual(service.geocoder.queries, [])
        self.assertEqual(result["geocoding_status"], "manual")
        self.assertEqual(result["geocoding_provider"], "manual")
        self.assertEqual(result["source"], "manual")
        self.assertIsNotNone(result["latitude"])
        self.assertIsNotNone(result["longitude"])
        self.assertIsNone(result["error"])


if __name__ == "__main__":
    unittest.main()
