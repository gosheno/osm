import unittest
from unittest.mock import patch

from app.clients.nominatim_client import GeocodingCandidate
from app.clients.opencage_client import (
    GeocodingCandidate as OpenCageCandidate,
    OpenCageConfigError,
)
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

    def all(self):
        if self.row is None:
            return []
        if isinstance(self.row, list):
            return self.row
        return [self.row]


class FakeDb:
    def __init__(self, existing=None, similar=None):
        self.existing = existing
        self.similar = similar
        self.execute_calls = []
        self.commits = 0

    async def execute(self, statement, params):
        statement_text = str(statement)
        self.execute_calls.append((statement_text, params))

        if "SELECT" in statement_text and "FROM addresses" in statement_text:
            if "geocoding_status = 'found'" in statement_text:
                return FakeMappingResult(self.similar)
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
        self.contexts = []

    async def search(self, query, limit=5, context=None):
        self.queries.append(query)
        self.contexts.append(context)
        return self.candidates


class FailingGeocoder:
    def __init__(self, error):
        self.error = error
        self.queries = []
        self.contexts = []

    async def search(self, query, limit=5, context=None):
        self.queries.append(query)
        self.contexts.append(context)
        raise self.error


class FakeOpenCageClient:
    def __init__(self, candidates):
        self.candidates = candidates
        self.queries = []

    async def search(self, query, limit=5):
        self.queries.append((query, limit))
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
            ["Санкт-Петербург, невский проспект дом 9"],
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
            ["Санкт-Петербург, невский проспект дом 9"],
        )
        self.assertEqual(result["source"], "nominatim")
        saved_addresses = [
            params["original_address"]
            for _, params in db.execute_calls
            if "original_address" in params
        ]
        self.assertIn("СПБ, Невский пр-т д. 9", saved_addresses)

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

    async def test_cached_found_outside_work_area_is_retried(self):
        db = FakeDb(
            existing={
                "id": 8,
                "original_address": "\u041d\u0443\u0440\u043c\u0430 12",
                "normalized_address": "\u043d\u0443\u0440\u043c\u0430 12",
                "latitude": 56.7088827,
                "longitude": 47.7113122,
                "geocoding_status": "found",
                "geocoding_provider": "nominatim",
                "confidence_score": 100.0,
            }
        )
        service = AddressService(db)
        service.geocoder = FakeGeocoder(
            [
                GeocodingCandidate(
                    latitude=59.5621642,
                    longitude=31.0166627,
                    display_name=(
                        "\u0428\u0430\u043f\u043a\u0438\u043d\u0441\u043a\u0430\u044f "
                        "\u0443\u043b\u0438\u0446\u0430, 12, \u041d\u0443\u0440\u043c\u0430, "
                        "\u041b\u0435\u043d\u0438\u043d\u0433\u0440\u0430\u0434\u0441\u043a\u0430\u044f "
                        "\u043e\u0431\u043b\u0430\u0441\u0442\u044c"
                    ),
                    importance=0.8,
                    place_rank=30,
                    raw={"address": {"house_number": "12"}},
                )
            ]
        )

        result = await service.geocode_address(
            "\u041d\u0443\u0440\u043c\u0430 12",
            default_city="\u041a\u0438\u0440\u0438\u0448\u0438, \u041b\u0435\u043d\u0438\u043d\u0433\u0440\u0430\u0434\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c",
        )

        self.assertTrue(service.geocoder.queries)
        self.assertEqual(result["source"], "nominatim")
        self.assertEqual(result["geocoding_status"], "found")
        self.assertEqual(result["latitude"], 59.5621642)
        self.assertEqual(result["longitude"], 31.0166627)

    async def test_geocode_uses_database_house_number_after_street_match(self):
        input_address = "\u041a\u043e\u043d\u0441\u0442\u0430\u043d\u0442\u0438\u043d\u043e\u0432\u0441\u043a\u0438\u0439 20"
        db = FakeDb(
            existing={
                "id": 10,
                "original_address": input_address,
                "normalized_address": "\u043a\u043e\u043d\u0441\u0442\u0430\u043d\u0442\u0438\u043d\u043e\u0432\u0441\u043a\u0438\u0439 20",
                "latitude": 59.9724297,
                "longitude": 30.269809,
                "geocoding_status": "ambiguous",
                "geocoding_provider": "nominatim",
                "confidence_score": 0.01,
            },
            similar={
                "id": 11,
                "original_address": "\u0421\u0430\u043d\u043a\u0442-\u041f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433, \u041a\u043e\u043d\u0441\u0442\u0430\u043d\u0442\u0438\u043d\u043e\u0432\u0441\u043a\u0438\u0439 \u043f\u0440\u043e\u0441\u043f\u0435\u043a\u0442, 20\u0410",
                "normalized_address": "\u0441\u0430\u043d\u043a\u0442-\u043f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433, \u043a\u043e\u043d\u0441\u0442\u0430\u043d\u0442\u0438\u043d\u043e\u0432\u0441\u043a\u0438\u0439 \u043f\u0440\u043e\u0441\u043f\u0435\u043a\u0442, 20\u0430",
                "latitude": 59.9725226,
                "longitude": 30.2696541,
                "geocoding_status": "found",
                "geocoding_provider": "known_poi",
                "confidence_score": 95.0,
                "display_name": "\u0421\u0430\u043d\u043a\u0442-\u041f\u0435\u0442\u0435\u0440\u0431\u0443\u0440\u0433, \u041a\u043e\u043d\u0441\u0442\u0430\u043d\u0442\u0438\u043d\u043e\u0432\u0441\u043a\u0438\u0439 \u043f\u0440\u043e\u0441\u043f\u0435\u043a\u0442, 20\u0410",
            },
        )
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])

        result = await service.geocode_address(input_address, default_city=None)

        self.assertEqual(service.geocoder.queries, [])
        self.assertEqual(result["source"], "database")
        self.assertEqual(result["geocoding_status"], "found")
        self.assertEqual(result["geocoding_provider"], "known_poi")
        self.assertEqual(result["latitude"], 59.9725226)
        self.assertEqual(result["longitude"], 30.2696541)

    async def test_geocode_does_not_match_different_street_by_region_and_house_only(self):
        input_address = "\u0420\u044b\u0447\u0438\u043d\u0430 14"
        db = FakeDb(
            similar=[
                {
                    "id": 15,
                    "original_address": "\u041a\u0438\u0440\u0438\u0448\u0438, \u0443\u043b\u0438\u0446\u0430 \u0413\u0435\u0440\u043e\u0435\u0432, 14\u0410",
                    "normalized_address": "\u043a\u0438\u0440\u0438\u0448\u0438, \u043b\u0435\u043d\u0438\u043d\u0433\u0440\u0430\u0434\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c, \u0433\u0435\u0440\u043e\u0435\u0432 14\u0430",
                    "latitude": 59.4440116,
                    "longitude": 32.024451,
                    "geocoding_status": "found",
                    "geocoding_provider": "nominatim",
                    "confidence_score": 95.0,
                    "display_name": "\u041a\u0438\u0440\u0438\u0448\u0438, \u0443\u043b\u0438\u0446\u0430 \u0413\u0435\u0440\u043e\u0435\u0432, 14\u0410",
                }
            ],
        )
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])
        fallback = FakeOpenCageClient([])

        with patch("app.services.address_service.OpenCageClient", return_value=fallback):
            result = await service.geocode_address(
                input_address,
                default_city="\u041a\u0438\u0440\u0438\u0448\u0438, \u041b\u0435\u043d\u0438\u043d\u0433\u0440\u0430\u0434\u0441\u043a\u0430\u044f \u043e\u0431\u043b\u0430\u0441\u0442\u044c",
            )

        self.assertEqual(result["geocoding_status"], "not_found")
        self.assertEqual(result["source"], "opencage")
        self.assertIsNone(result["id"])
        self.assertIsNone(result["latitude"])
        self.assertIsNone(result["longitude"])

    async def test_geocode_handles_no_candidates_as_not_found(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])
        fallback = FakeOpenCageClient([])

        with patch("app.services.address_service.OpenCageClient", return_value=fallback):
            result = await service.geocode_address("СПБ, Невский пр-т д. 9")

        self.assertIsNone(result["latitude"])
        self.assertIsNone(result["longitude"])
        self.assertEqual(result["geocoding_status"], "not_found")
        self.assertEqual(result["geocoding_provider"], "opencage")
        self.assertEqual(result["source"], "opencage")
        self.assertEqual(result["error"], "Address was not found")
        self.assertIsNone(result["id"])
        self.assertFalse(
            any(
                "INSERT INTO addresses" in statement
                for statement, _params in db.execute_calls
            )
        )
        self.assertIn(
            ("Санкт-Петербург, невский проспект дом 9", 5),
            fallback.queries,
        )

    async def test_geocoding_area_uses_viewbox_without_adding_area_to_query(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder(
            [
                GeocodingCandidate(
                    latitude=59.9109,
                    longitude=29.7791,
                    display_name=(
                        "Швейцарская улица, 14, Троицкая слобода, "
                        "Ломоносов, Санкт-Петербург, Россия"
                    ),
                    importance=0.8,
                    place_rank=30,
                    raw={"address": {"house_number": "14"}},
                )
            ]
        )

        result = await service.geocode_address(
            "Швейцарская 14",
            default_city="Санкт-Петербург",
            geocoding_area="Петергоф",
        )

        self.assertEqual(service.geocoder.queries, ["улица швейцарская 14"])
        self.assertEqual(result["normalized_address"], "швейцарская 14")
        self.assertEqual(result["geocoding_context_label"], "Петергоф")
        self.assertEqual(result["geocoding_status"], "found")
        self.assertEqual(result["source"], "nominatim")
        self.assertTrue(service.geocoder.contexts[0].bounded)

    async def test_explicit_context_keeps_default_city_out_of_normalized_address(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])
        fallback = FakeOpenCageClient([])

        with patch("app.services.address_service.OpenCageClient", return_value=fallback):
            result = await service.geocode_address(
                "Новоселье 4",
                default_city="Санкт-Петербург",
                geocoding_context={"type": "default_spb", "bounded": False},
            )

        self.assertEqual(result["normalized_address"], "новоселье 4")
        self.assertIn("новоселье 4", service.geocoder.queries)
        self.assertNotEqual(
            result["normalized_address"],
            "санкт-петербург, новоселье 4",
        )

    async def test_cached_not_found_is_retried_instead_of_returned_from_database(self):
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
        fallback = FakeOpenCageClient([])

        with patch("app.services.address_service.OpenCageClient", return_value=fallback):
            result = await service.geocode_address("string")

        self.assertIn("Санкт-Петербург, string", service.geocoder.queries)
        self.assertIn(("Санкт-Петербург, string", 5), fallback.queries)
        self.assertIsNone(result["id"])
        self.assertEqual(result["geocoding_status"], "not_found")
        self.assertEqual(result["source"], "opencage")
        self.assertEqual(result["error"], "Address was not found")
        self.assertEqual(db.commits, 0)
        self.assertFalse(
            any(
                "INSERT INTO addresses" in statement
                for statement, _params in db.execute_calls
            )
        )

    async def test_cached_not_found_is_not_replaced_by_manual_demo_coordinates(self):
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
        fallback = FakeOpenCageClient([])

        with patch("app.services.address_service.OpenCageClient", return_value=fallback):
            result = await service.geocode_address("Санкт-Петербург, 6-я линия В.О. 15")

        self.assertTrue(service.geocoder.queries)
        self.assertEqual(len(fallback.queries), len(service.geocoder.queries))
        self.assertEqual(result["geocoding_status"], "not_found")
        self.assertEqual(result["geocoding_provider"], "opencage")
        self.assertEqual(result["source"], "opencage")
        self.assertIsNone(result["latitude"])
        self.assertIsNone(result["longitude"])
        self.assertEqual(result["error"], "Address was not found")
        self.assertIsNone(result["id"])
        self.assertFalse(
            any(
                "INSERT INTO addresses" in statement
                for statement, _params in db.execute_calls
            )
        )

    async def test_kirishi_address_uses_regional_queries_instead_of_manual_coordinates(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])
        fallback = FakeOpenCageClient([])

        with patch("app.services.address_service.OpenCageClient", return_value=fallback):
            result = await service.geocode_address(
                "Нефтехимиков 18А",
                default_city="Кириши, Ленинградская область",
            )

        self.assertEqual(
            service.geocoder.queries,
            [
                "Ленинградская область, кириши, нефтехимиков 18а",
                "кириши, нефтехимиков 18а, Ленинградская область",
                "кириши, ленинградская область, нефтехимиков 18а",
            ],
        )
        self.assertEqual(result["geocoding_status"], "not_found")
        self.assertEqual(result["geocoding_provider"], "opencage")
        self.assertEqual(result["source"], "opencage")
        self.assertIsNone(result["latitude"])
        self.assertIsNone(result["longitude"])
        self.assertEqual(result["error"], "Address was not found")
        self.assertIsNone(result["id"])
        self.assertFalse(
            any(
                "INSERT INTO addresses" in statement
                for statement, _params in db.execute_calls
            )
        )

    async def test_nominatim_empty_result_falls_back_to_opencage(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])
        fallback = FakeOpenCageClient(
            [
                OpenCageCandidate(
                    latitude=59.9386,
                    longitude=30.3141,
                    display_name="Невский проспект, 9, Санкт-Петербург, Россия",
                    confidence=9,
                )
            ]
        )

        with patch("app.services.address_service.OpenCageClient", return_value=fallback):
            result = await service.geocode_address("СПБ, Невский пр-т д. 9")

        self.assertEqual(result["geocoding_status"], "found")
        self.assertEqual(result["geocoding_provider"], "opencage")
        self.assertEqual(result["source"], "opencage")
        self.assertEqual(result["latitude"], 59.9386)
        self.assertEqual(result["longitude"], 30.3141)
        self.assertEqual(
            fallback.queries,
            [("Санкт-Петербург, невский проспект дом 9", 5)],
        )

    async def test_nominatim_error_falls_back_to_opencage(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FailingGeocoder(RuntimeError("Nominatim 429"))
        fallback = FakeOpenCageClient(
            [
                OpenCageCandidate(
                    latitude=59.9386,
                    longitude=30.3141,
                    display_name="Невский проспект, 9, Санкт-Петербург, Россия",
                    confidence=9,
                )
            ]
        )

        with patch("app.services.address_service.OpenCageClient", return_value=fallback):
            result = await service.geocode_address("СПБ, Невский пр-т д. 9")

        self.assertEqual(service.geocoder.queries, ["Санкт-Петербург, невский проспект дом 9"])
        self.assertEqual(result["geocoding_status"], "found")
        self.assertEqual(result["geocoding_provider"], "opencage")
        self.assertEqual(result["source"], "opencage")

    async def test_missing_opencage_key_returns_error_without_caching_not_found(self):
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder([])

        with patch(
            "app.services.address_service.OpenCageClient",
            side_effect=OpenCageConfigError("OPENCAGE_API_KEY is not set"),
        ):
            result = await service.geocode_address("СПБ, Невский пр-т д. 9")

        self.assertEqual(result["geocoding_status"], "error")
        self.assertEqual(result["geocoding_provider"], "opencage")
        self.assertEqual(result["source"], "opencage")
        self.assertIn("OPENCAGE_API_KEY", result["error"])
        self.assertFalse(
            any(
                "INSERT INTO addresses" in statement
                for statement, _params in db.execute_calls
            )
        )

    async def test_geocode_with_opencage_provider_stores_opencage_provider(self):
        """Test that when using OpenCage provider, geocoding_provider is set to 'opencage'."""
        # Create OpenCage-style candidate with confidence instead of importance
        from dataclasses import dataclass
        
        @dataclass
        class OpenCageCandidate:
            latitude: float
            longitude: float
            display_name: str
            confidence: int = None
        
        db = FakeDb()
        service = AddressService(db)
        service.geocoder = FakeGeocoder(
            [
                OpenCageCandidate(
                    latitude=55.7558,
                    longitude=37.6173,
                    display_name="Москва, Россия",
                    confidence=9,
                )
            ]
        )
        
        # Mock settings to return opencage as provider
        with patch("app.services.address_service.settings") as mock_settings:
            mock_settings.GEOCODER_PROVIDER = "opencage"
            
            result = await service.geocode_address("Москва")
        
        self.assertEqual(result["geocoding_provider"], "opencage")
        self.assertEqual(result["source"], "opencage")
        self.assertEqual(result["latitude"], 55.7558)
        self.assertEqual(result["longitude"], 37.6173)
        self.assertEqual(result["confidence_score"], 9.0)  # OpenCage: confidence as-is
        self.assertIsNone(result["error"])


if __name__ == "__main__":
    unittest.main()
