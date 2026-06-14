import unittest

from app.schemas.address import AddressSuggestionItem
from app.services.address_suggestions import (
    extract_street_text,
    item_is_street_completion,
    query_has_house_number,
    sort_suggestion_items,
    street_completion_items_from_items,
    street_completion_matches_query,
)


def suggestion(
    *,
    item_id: str,
    address: dict,
    confidence_score: float,
    source: str = "nominatim",
    category: str | None = None,
    item_type: str | None = None,
    display_name: str | None = None,
    main_text: str | None = None,
) -> AddressSuggestionItem:
    return AddressSuggestionItem(
        id=item_id,
        provider=source,
        display_name=display_name or item_id,
        main_text=main_text or display_name or item_id,
        latitude=59.0,
        longitude=30.0,
        category=category,
        type=item_type,
        confidence_score=confidence_score,
        address=address,
        source=source,
    )


class AddressSuggestionSortTests(unittest.TestCase):
    def test_street_suggestions_are_first_before_house_is_typed(self):
        house = suggestion(
            item_id="house",
            address={"road": "Невский проспект", "house_number": "114"},
            confidence_score=100,
            source="database",
        )
        street = suggestion(
            item_id="street",
            address={"road": "Невский проспект"},
            confidence_score=30,
            source="nominatim",
            category="highway",
            item_type="primary",
        )

        items = sort_suggestion_items([house, street], query="Невский")

        self.assertEqual(items[0].id, "street")
        self.assertFalse(query_has_house_number("3-я линия"))
        self.assertFalse(query_has_house_number("3-я"))
        self.assertTrue(query_has_house_number("3-я линия 2"))
        self.assertTrue(query_has_house_number("улица Кораблестроителей 32 к1"))
        self.assertTrue(item_is_street_completion(street))
        self.assertFalse(item_is_street_completion(house))

    def test_partial_street_query_promotes_matching_street(self):
        house = suggestion(
            item_id="house",
            address={"road": "улица Кораблестроителей", "house_number": "16"},
            confidence_score=100,
            source="database",
        )
        street = suggestion(
            item_id="street",
            address={"road": "улица Кораблестроителей"},
            confidence_score=30,
            source="nominatim",
            category="highway",
            item_type="road",
        )

        items = sort_suggestion_items([house, street], query="кораб")

        self.assertEqual(items[0].id, "street")
        self.assertTrue(street_completion_matches_query(street, "кораб"))

    def test_cached_house_can_create_street_completion(self):
        cached_house = suggestion(
            item_id="cached-house",
            address={},
            confidence_score=100,
            source="database",
            display_name="Кораблестроителей ул, 16",
        )

        items = street_completion_items_from_items([cached_house], query="кораб")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].main_text, "улица Кораблестроителей")
        self.assertEqual(items[0].address["road"], "улица Кораблестроителей")
        self.assertTrue(item_is_street_completion(items[0]))

    def test_extracts_street_from_full_display_address(self):
        self.assertEqual(
            extract_street_text("Санкт-Петербург, улица Кораблестроителей, 32 к1"),
            "улица Кораблестроителей",
        )

    def test_house_query_keeps_specific_cached_address_first(self):
        house = suggestion(
            item_id="house",
            address={"road": "Невский проспект", "house_number": "114"},
            confidence_score=100,
            source="database",
        )
        street = suggestion(
            item_id="street",
            address={"road": "Невский проспект"},
            confidence_score=30,
            source="nominatim",
            category="highway",
            item_type="primary",
        )

        items = sort_suggestion_items([street, house], query="Невский 114")

        self.assertTrue(query_has_house_number("Невский 114"))
        self.assertEqual(items[0].id, "house")

    def test_unrelated_street_is_not_promoted_by_neighbourhood_match(self):
        house = suggestion(
            item_id="house",
            address={"road": "Невский проспект", "house_number": "114"},
            confidence_score=100,
            source="database",
        )
        unrelated_street = suggestion(
            item_id="unrelated-street",
            address={"road": "Дегтярная улица", "neighbourhood": "Невский 140"},
            confidence_score=60,
            source="nominatim",
            category="highway",
            item_type="residential",
        )

        items = sort_suggestion_items([unrelated_street, house], query="Невский")

        self.assertEqual(items[0].id, "house")


if __name__ == "__main__":
    unittest.main()
