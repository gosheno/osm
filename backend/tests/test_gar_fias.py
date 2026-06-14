import tempfile
import unittest
from pathlib import Path

from app.services.gar_importer import (
    GarImportService,
    classify_xml_file,
    normalize_region_codes,
)
from app.services.gar_normalizer import (
    normalize_house_value,
    normalize_lookup_text,
    street_name_without_type,
)


class GarImporterTests(unittest.TestCase):
    def test_region_preset_expands_to_spb_and_lenobl(self):
        self.assertEqual(normalize_region_codes("spb_lenobl"), ["78", "47"])
        self.assertEqual(normalize_region_codes("78,47"), ["78", "47"])

    def test_classifies_common_gar_xml_names(self):
        self.assertEqual(classify_xml_file(Path("AS_ADM_HIERARCHY_2026.XML")), "hierarchy")
        self.assertEqual(classify_xml_file(Path("AS_ADDR_OBJ_2026.XML")), "objects")
        self.assertEqual(classify_xml_file(Path("AS_HOUSES_2026.XML")), "houses")

    def test_reads_hierarchy_and_builds_rows(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            hierarchy_path = Path(temp_dir) / "AS_ADM_HIERARCHY.XML"
            hierarchy_path.write_text(
                """
                <ROOT>
                  <ITEM OBJECTID="100" PARENTOBJID="10" REGIONCODE="78" PATH="10.100" ISACTIVE="1" />
                  <ITEM OBJECTID="200" PARENTOBJID="100" REGIONCODE="78" PATH="10.100.200" ISACTIVE="1" />
                </ROOT>
                """,
                encoding="utf-8",
            )

            service = GarImportService(db=None)  # type: ignore[arg-type]
            hierarchy = service._read_hierarchy([hierarchy_path], ["78"])

        object_row = service._object_row(
            {
                "OBJECTID": "100",
                "OBJECTGUID": "street-guid",
                "NAME": "Кораблестроителей",
                "TYPENAME": "ул",
                "LEVEL": "8",
                "ISACTUAL": "1",
            },
            hierarchy,
        )
        house_row = service._house_row(
            {
                "OBJECTID": "200",
                "OBJECTGUID": "house-guid",
                "HOUSEID": "200",
                "HOUSENUM": "14",
                "ADDNUM1": "2",
                "ISACTUAL": "1",
            },
            hierarchy,
        )

        self.assertEqual(object_row["parent_object_id"], 10)
        self.assertEqual(object_row["full_name"], "улица Кораблестроителей")
        self.assertEqual(object_row["region_code"], "78")
        self.assertEqual(house_row["parent_object_id"], 100)
        self.assertEqual(house_row["house_number"], "14")
        self.assertEqual(house_row["building_number"], "2")


class GarNormalizerHelpersTests(unittest.TestCase):
    def test_normalizes_lookup_text(self):
        self.assertEqual(normalize_lookup_text("СПБ,  Ленинский пр-т"), "спб ленинский пр-т")

    def test_strips_street_type_for_lookup(self):
        self.assertEqual(street_name_without_type("улица Кораблестроителей"), "кораблестроителей")
        self.assertEqual(street_name_without_type("3-я линия"), "3-я")

    def test_normalizes_house_value(self):
        self.assertEqual(normalize_house_value("д. 32 к 1"), "32к1")
        self.assertEqual(normalize_house_value("14 корпус 2"), "14к2")


if __name__ == "__main__":
    unittest.main()
