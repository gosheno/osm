import unittest
from urllib.parse import parse_qs, urlparse

from app.schemas.yandex_links import (
    BuildYandexLinksRequest,
    YandexLinkBatchInput,
    YandexLinkPointInput,
)
from app.services.yandex_link_builder import (
    YandexLinkValidationError,
    add_yandex_links_to_batches,
    build_ll,
    build_rtext,
    build_yandex_maps_url,
    format_yandex_ll,
    format_yandex_rtext_point,
)


def point(
    batch_order: int,
    global_order: int,
    *,
    point_type: str = "waypoint",
    label: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    is_transition_point: bool = False,
) -> YandexLinkPointInput:
    return YandexLinkPointInput(
        batch_order=batch_order,
        global_order=global_order,
        type=point_type,
        label=label,
        latitude=latitude if latitude is not None else 59.9 + global_order * 0.01,
        longitude=longitude if longitude is not None else 30.3 + global_order * 0.01,
        original_index=global_order,
        is_transition_point=is_transition_point,
    )


class YandexLinkBuilderTests(unittest.TestCase):
    def test_formats_rtext_as_lat_lon_and_ll_as_lon_lat(self):
        test_point = point(
            0,
            0,
            latitude=59.9398,
            longitude=30.3141,
            point_type="start",
        )

        self.assertEqual(
            format_yandex_rtext_point(test_point),
            "59.939800,30.314100",
        )
        self.assertEqual(
            format_yandex_ll((59.9398, 30.3141)),
            "30.314100,59.939800",
        )

    def test_builds_one_batch_two_point_url(self):
        batch = YandexLinkBatchInput(
            batch_number=1,
            points=[
                point(0, 0, point_type="start", latitude=59.9398, longitude=30.3141),
                point(1, 1, point_type="end", latitude=59.9297, longitude=30.3627),
            ],
        )

        url = build_yandex_maps_url(batch)
        parsed = urlparse(url)
        query = parse_qs(parsed.query)

        self.assertEqual(parsed.scheme, "https")
        self.assertEqual(parsed.netloc, "yandex.ru")
        self.assertEqual(parsed.path, "/maps/2/saint-petersburg/")
        self.assertEqual(query["mode"], ["routes"])
        self.assertEqual(query["rtn"], ["1"])
        self.assertEqual(query["rtt"], ["auto"])
        self.assertEqual(
            query["rtext"],
            ["59.939800,30.314100~59.929700,30.362700"],
        )
        self.assertIn(
            "rtext=59.939800%2C30.314100~59.929700%2C30.362700",
            url,
        )

    def test_builds_one_batch_three_point_url_in_batch_order(self):
        batch = YandexLinkBatchInput(
            batch_number=1,
            points=[
                point(2, 2, point_type="end", latitude=59.9297, longitude=30.3627),
                point(0, 0, point_type="start", latitude=59.9398, longitude=30.3141),
                point(1, 1, latitude=59.9488, longitude=30.3359),
            ],
        )
        sorted_points = [
            point(0, 0, point_type="start", latitude=59.9398, longitude=30.3141),
            point(1, 1, latitude=59.9488, longitude=30.3359),
            point(2, 2, point_type="end", latitude=59.9297, longitude=30.3627),
        ]

        self.assertEqual(
            build_rtext(sorted_points),
            "59.939800,30.314100~59.948800,30.335900~59.929700,30.362700",
        )
        self.assertEqual(build_ll(sorted_points), "30.337567,59.939433")

        response = add_yandex_links_to_batches(
            BuildYandexLinksRequest(
                city_slug="saint-petersburg",
                batches=[batch],
            )
        )

        self.assertEqual(response.status, "completed")
        self.assertEqual(
            [item.batch_order for item in response.batches[0].points],
            [0, 1, 2],
        )

    def test_builds_two_batch_urls_with_transition_point(self):
        response = add_yandex_links_to_batches(
            BuildYandexLinksRequest(
                city_slug="saint-petersburg",
                batches=[
                    YandexLinkBatchInput(
                        batch_number=1,
                        points=[
                            point(0, 0, point_type="start"),
                            point(1, 1),
                            point(2, 2),
                        ],
                    ),
                    YandexLinkBatchInput(
                        batch_number=2,
                        points=[
                            point(0, 2, is_transition_point=True),
                            point(1, 3),
                            point(2, 4, point_type="end"),
                        ],
                    ),
                ],
            )
        )

        self.assertEqual(response.status, "completed")
        self.assertEqual(response.batches_count, 2)
        self.assertEqual(response.batches[0].points[0].global_order, 0)
        self.assertEqual(response.batches[1].points[0].global_order, 2)
        self.assertTrue(response.batches[1].points[0].is_transition_point)
        self.assertIn("mode=routes", response.batches[0].yandex_maps_url)
        self.assertIn("rtt=auto", response.batches[1].yandex_maps_url)

    def test_warns_when_city_slug_defaulted_or_url_too_long(self):
        response = add_yandex_links_to_batches(
            BuildYandexLinksRequest(
                max_url_length=50,
                batches=[
                    YandexLinkBatchInput(
                        batch_number=1,
                        points=[
                            point(0, 0, point_type="start"),
                            point(1, 1, point_type="end"),
                        ],
                    )
                ],
            )
        )

        self.assertEqual(response.status, "completed_with_warnings")
        self.assertIn(
            "City slug was not provided, default value used",
            response.batches[0].warnings,
        )
        self.assertIn(
            "URL length exceeds recommended limit",
            response.batches[0].warnings,
        )

    def test_warns_when_later_batch_transition_point_is_missing(self):
        response = add_yandex_links_to_batches(
            BuildYandexLinksRequest(
                city_slug="saint-petersburg",
                batches=[
                    YandexLinkBatchInput(
                        batch_number=1,
                        points=[point(0, 0, point_type="start"), point(1, 1)],
                    ),
                    YandexLinkBatchInput(
                        batch_number=2,
                        points=[point(0, 2), point(1, 3, point_type="end")],
                    ),
                ],
            )
        )

        self.assertEqual(response.status, "completed_with_warnings")
        self.assertIn("Transition point is missing", response.batches[1].warnings)

    def test_rejects_empty_batches(self):
        with self.assertRaisesRegex(YandexLinkValidationError, "batches must not be empty"):
            add_yandex_links_to_batches(BuildYandexLinksRequest(batches=[]))

    def test_rejects_batch_with_less_than_two_points(self):
        with self.assertRaisesRegex(YandexLinkValidationError, "at least two points"):
            add_yandex_links_to_batches(
                BuildYandexLinksRequest(
                    city_slug="saint-petersburg",
                    batches=[
                        YandexLinkBatchInput(
                            batch_number=1,
                            points=[point(0, 0, point_type="start")],
                        )
                    ],
                )
            )

    def test_rejects_duplicate_batch_number(self):
        with self.assertRaisesRegex(YandexLinkValidationError, "duplicate batch_number"):
            add_yandex_links_to_batches(
                BuildYandexLinksRequest(
                    city_slug="saint-petersburg",
                    batches=[
                        YandexLinkBatchInput(
                            batch_number=1,
                            points=[point(0, 0), point(1, 1)],
                        ),
                        YandexLinkBatchInput(
                            batch_number=1,
                            points=[point(0, 2), point(1, 3)],
                        ),
                    ],
                )
            )

    def test_rejects_duplicate_batch_order(self):
        with self.assertRaisesRegex(YandexLinkValidationError, "duplicate batch_order"):
            add_yandex_links_to_batches(
                BuildYandexLinksRequest(
                    city_slug="saint-petersburg",
                    batches=[
                        YandexLinkBatchInput(
                            batch_number=1,
                            points=[point(0, 0), point(0, 1)],
                        )
                    ],
                )
            )

    def test_rejects_invalid_city_slug(self):
        with self.assertRaisesRegex(YandexLinkValidationError, "invalid city_slug"):
            add_yandex_links_to_batches(
                BuildYandexLinksRequest(
                    city_slug="Санкт-Петербург",
                    batches=[
                        YandexLinkBatchInput(
                            batch_number=1,
                            points=[point(0, 0), point(1, 1)],
                        )
                    ],
                )
            )

    def test_rejects_unsupported_route_type(self):
        with self.assertRaisesRegex(YandexLinkValidationError, "unsupported route_type"):
            add_yandex_links_to_batches(
                BuildYandexLinksRequest(
                    city_slug="saint-petersburg",
                    route_type="pedestrian",
                    batches=[
                        YandexLinkBatchInput(
                            batch_number=1,
                            points=[point(0, 0), point(1, 1)],
                        )
                    ],
                )
            )


if __name__ == "__main__":
    unittest.main()
