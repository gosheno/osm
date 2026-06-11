import unittest

from app.utils.address_normalizer import normalize_address


class AddressNormalizerTests(unittest.TestCase):
    def test_extracts_place_name_before_comma_address(self):
        result = normalize_address("Пятёрочка, СПБ, Невский пр-т д. 9")

        self.assertEqual(result.place_name, "Пятёрочка")
        self.assertEqual(result.address_for_geocoding, "СПБ, Невский пр-т д. 9")
        self.assertEqual(
            result.normalized_address,
            "санкт-петербург, невский проспект дом 9",
        )
        self.assertNotIn("пятерочка", result.tokens)

    def test_extracts_place_name_with_explicit_separator(self):
        result = normalize_address("24 часа — СПБ, Невский пр-т д. 9")

        self.assertEqual(result.place_name, "24 часа")
        self.assertEqual(result.address_for_geocoding, "СПБ, Невский пр-т д. 9")
        self.assertEqual(
            result.normalized_address,
            "санкт-петербург, невский проспект дом 9",
        )

    def test_does_not_extract_place_when_input_starts_with_city(self):
        result = normalize_address("СПБ, Невский пр-т д. 9")

        self.assertIsNone(result.place_name)
        self.assertEqual(result.address_for_geocoding, "СПБ, Невский пр-т д. 9")
        self.assertEqual(
            result.normalized_address,
            "санкт-петербург, невский проспект дом 9",
        )

    def test_explicit_place_name_keeps_address_field_as_geocoding_input(self):
        result = normalize_address(
            "СПБ, Невский пр-т д. 9",
            place_name="Магнит",
        )

        self.assertEqual(result.place_name, "Магнит")
        self.assertEqual(result.address_for_geocoding, "СПБ, Невский пр-т д. 9")
        self.assertEqual(
            result.normalized_address,
            "санкт-петербург, невский проспект дом 9",
        )

    def test_does_not_extract_address_like_first_segment(self):
        result = normalize_address("7 линия, д. 9")

        self.assertIsNone(result.place_name)
        self.assertEqual(
            result.normalized_address,
            "санкт-петербург, 7 линия, дом 9",
        )

    def test_expands_vasileostrovsky_abbreviation_for_line_addresses(self):
        result = normalize_address("Санкт-Петербург, 6-я линия В.О. 15")

        self.assertEqual(
            result.normalized_address,
            "санкт-петербург, 6-я линия васильевский остров 15",
        )

    def test_uses_non_spb_default_city_for_short_regional_address(self):
        result = normalize_address(
            "Нефтехимиков 18А",
            default_city="Кириши, Ленинградская обл.",
        )

        self.assertEqual(
            result.normalized_address,
            "кириши, ленинградская область, нефтехимиков 18а",
        )

    def test_does_not_prefix_spb_to_full_lenoblast_address(self):
        result = normalize_address(
            "ул. Нефтехимиков, 18а, Кириши, Ленинградская обл.",
        )

        self.assertEqual(
            result.normalized_address,
            "улица нефтехимиков, 18а, кириши, ленинградская область",
        )


if __name__ == "__main__":
    unittest.main()
