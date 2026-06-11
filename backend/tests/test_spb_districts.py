import unittest

from app.services.spb_districts import infer_spb_district


class SpbDistrictTests(unittest.TestCase):
    def test_infers_central_district_from_known_street(self):
        self.assertEqual(
            infer_spb_district(
                latitude=None,
                longitude=None,
                address_text="Марата 65",
            ),
            "Центральный",
        )

    def test_infers_petrogradsky_district_from_ps_abbreviation(self):
        self.assertEqual(
            infer_spb_district(
                latitude=None,
                longitude=None,
                address_text="Малый пр. П.С., 66",
            ),
            "Петроградский",
        )

    def test_infers_petrodvortsovy_district_from_known_street(self):
        self.assertEqual(
            infer_spb_district(
                latitude=None,
                longitude=None,
                address_text="Бобыльская 59",
            ),
            "Петродворцовый",
        )

    def test_falls_back_to_coordinates_when_street_is_unknown(self):
        self.assertEqual(
            infer_spb_district(
                latitude=59.935,
                longitude=30.33,
                address_text="Неизвестная 1",
            ),
            "Адмиралтейский",
        )


if __name__ == "__main__":
    unittest.main()
