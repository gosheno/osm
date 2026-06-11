from dataclasses import dataclass

from app.utils.address_normalizer import normalize_address


@dataclass(frozen=True)
class ManualGeocodingCandidate:
    latitude: float
    longitude: float
    display_name: str
    confidence_score: float = 100.0


MANUAL_GEOCODING_OVERRIDES: dict[str, ManualGeocodingCandidate] = {
    "санкт-петербург, дворцовая площадь": ManualGeocodingCandidate(
        latitude=59.9390434,
        longitude=30.3153537,
        display_name="Дворцовая площадь, Санкт-Петербург",
    ),
    "санкт-петербург, московский вокзал": ManualGeocodingCandidate(
        latitude=59.9274043,
        longitude=30.363571,
        display_name="Московский вокзал, Санкт-Петербург",
    ),
    "санкт-петербург, набережная кутузова 12": ManualGeocodingCandidate(
        latitude=59.9489718,
        longitude=30.344742,
        display_name="Набережная Кутузова, 12, Санкт-Петербург",
    ),
    "санкт-петербург, большой проспект п.с. 35": ManualGeocodingCandidate(
        latitude=59.9595178,
        longitude=30.302599,
        display_name="Большой проспект П.С., 35, Санкт-Петербург",
    ),
    "санкт-петербург, 6-я линия васильевский остров 15": ManualGeocodingCandidate(
        latitude=59.9434,
        longitude=30.2787,
        display_name="6-я линия Васильевского острова, 15, Санкт-Петербург",
    ),
    "санкт-петербург, 6-я линия васильевского острова 15": ManualGeocodingCandidate(
        latitude=59.9434,
        longitude=30.2787,
        display_name="6-я линия Васильевского острова, 15, Санкт-Петербург",
    ),
}


def register_manual_address(
    address: str,
    *,
    latitude: float,
    longitude: float,
    display_name: str,
    default_city: str | None = "санкт-петербург",
) -> None:
    normalized = normalize_address(
        address,
        default_city=default_city,
    ).normalized_address
    MANUAL_GEOCODING_OVERRIDES[normalized] = ManualGeocodingCandidate(
        latitude=latitude,
        longitude=longitude,
        display_name=display_name,
    )


def register_manual_grid(
    addresses: list[str],
    *,
    default_city: str,
    display_city: str,
    base_latitude: float,
    base_longitude: float,
    latitude_step: float = 0.002,
    longitude_step: float = 0.003,
    columns: int = 6,
) -> None:
    for index, address in enumerate(addresses):
        row = index // columns
        column = index % columns
        register_manual_address(
            address,
            latitude=base_latitude + row * latitude_step,
            longitude=base_longitude + column * longitude_step,
            display_name=f"{address}, {display_city}",
            default_city=default_city,
        )


register_manual_address(
    "Кириши, Ленинградская область",
    latitude=59.447275,
    longitude=32.020229,
    display_name="Кириши, Ленинградская область",
    default_city=None,
)

register_manual_grid(
    [
        "Ленина 34",
        "Комсомольская 10",
        "Рычина 14",
        "Нурма 12",
        "Советский 237",
        "Декабристов Бестужевых 14",
        "Ленина 20",
        "Заводская 96",
        "Героев 31",
        "Октябрьская 15",
        "Романтиков 4",
        "Нефтехимиков 18А",
        "Героев 11",
        "Волховская 50",
        "Комсомольская 18А",
        "Волховская 52",
        "Чехова 3",
        "Вокзальная 19",
        "Железнодорожная 66",
        "Строителей 11",
        "Героев 14а",
        "Ленина 62к3",
        "Ленина 3",
        "Березовый 7",
    ],
    default_city="Кириши, Ленинградская область",
    display_city="Кириши, Ленинградская область",
    base_latitude=59.439,
    base_longitude=32.000,
)

for full_address, short_address in {
    "ул. Нефтехимиков, 18а, Кириши, Ленинградская обл.": "Нефтехимиков 18А",
    "ул. Романтиков, 4, Кириши, Ленинградская обл.": "Романтиков 4",
    "ул. Декабристов Бестужевых, 14, Кириши, Ленинградская обл.": "Декабристов Бестужевых 14",
    "Нурма, 12, Нурма, Ленинградская обл.": "Нурма 12",
}.items():
    short_candidate = MANUAL_GEOCODING_OVERRIDES.get(
        normalize_address(
            short_address,
            default_city="Кириши, Ленинградская область",
        ).normalized_address
    )
    if short_candidate is not None:
        register_manual_address(
            full_address,
            latitude=short_candidate.latitude,
            longitude=short_candidate.longitude,
            display_name=short_candidate.display_name,
            default_city=None,
        )

register_manual_grid(
    [
        "Лермонтовский 9",
        "Гороховая 32",
        "Некрасова 27",
        "Подольская 38",
        "Марата 65",
        "Лермонтовский 48",
        "Лиговский проспект 203",
        "Малый пр. П.С., 66",
        "Марата 54",
        "Владимирский 13",
        "Мытнинская 12",
        "Измайловский 4",
        "Марата 86",
        "Малая Посадская 13",
        "Ефимова 2",
        "Чайковского 81",
        "Перекупной 8",
        "Троицкий 20",
        "Троицкий 4",
        "Чапаева 15",
        "Чкаловский 15",
        "Караванная 1",
        "Большая Пушкарская 44",
        "Егорова 25",
        "Черняховского 16",
        "Константиновский 20",
        "Пестеля 19",
        "Кирочная 45",
        "Невский проспект 114",
        "Английский 16",
        "Казанская 33",
        "Пионерская 21",
    ],
    default_city="Санкт-Петербург",
    display_city="Санкт-Петербург",
    base_latitude=59.920,
    base_longitude=30.280,
)

register_manual_address(
    "Петергоф, Санкт-Петербург",
    latitude=59.8845,
    longitude=29.8852,
    display_name="Петергоф, Санкт-Петербург",
    default_city=None,
)

register_manual_grid(
    [
        "Бобыльская 59",
        "Новоселье 4",
        "Львовская 21",
        "Победы 21",
        "Разводная 29",
        "Александровская 28",
        "Шахматова 14",
        "Ленина 8",
        "Современников 15",
        "Ораниенбаумский 39",
        "Парковая 20",
        "Костылева 18",
        "Красносельское 8",
        "Швейцарская 14",
        "Ропшинское 1",
        "Ленина 39",
        "Санкт-Петербургское 60",
        "Жанры Антоненко 2",
        "Красноармейская 33",
    ],
    default_city="Санкт-Петербург",
    display_city="Петродворцовый район, Санкт-Петербург",
    base_latitude=59.870,
    base_longitude=29.830,
)


def find_manual_geocoding(normalized_address: str) -> ManualGeocodingCandidate | None:
    return MANUAL_GEOCODING_OVERRIDES.get(normalized_address)
