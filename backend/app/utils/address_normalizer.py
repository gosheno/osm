import re
from dataclasses import dataclass


@dataclass(frozen=True)
class NormalizedAddress:
    original_address: str
    address_for_geocoding: str
    normalized_address: str
    tokens: list[str]
    place_name: str | None = None


REPLACEMENTS = [
    (r"\bг\.\s*", ""),
    (r"\bгород\s+", ""),

    (r"\bспб\b", "санкт-петербург"),
    (r"\bс\.?\s*петербург\b", "санкт-петербург"),
    (r"\bсанкт петербург\b", "санкт-петербург"),
    (r"\bпитер\b", "санкт-петербург"),
    (r"\bлен(?:инградская)?\.?\s*обл\.?(?=\s|,|$)", "ленинградская область"),
    (r"\bленобласть\b", "ленинградская область"),

    (r"\bул\.?(?=\s|,|$)\s*", "улица "),
    (r"\bулиц[аы]\b", "улица"),

    (r"\bпр-т\.?(?=\s|,|$)\s*", "проспект "),
    (r"\bпросп\.?(?=\s|,|$)\s*", "проспект "),
    (r"\bпр\.?(?=\s|,|$)\s*", "проспект "),

    (r"\bнаб\.?(?=\s|,|$)\s*", "набережная "),
    (r"\bпер\.?(?=\s|,|$)\s*", "переулок "),
    (r"\bпл\.?(?=\s|,|$)\s*", "площадь "),
    (r"\bш\.?(?=\s|,|$)\s*", "шоссе "),
    (r"\bб-р\.?(?=\s|,|$)\s*", "бульвар "),
    (r"\bбул\.?(?=\s|,|$)\s*", "бульвар "),
    (r"\bбульв\.?(?=\s|,|$)\s*", "бульвар "),
    (r"\bв\.\s*о\.", "васильевский остров "),

    (r"\bд\.?(?=\s|,|$)\s*", "дом "),
    (r"\bдом\s+", "дом "),

    (r"\bкорп\.?(?=\s|,|$)\s*", "корпус "),
    (r"\bк\.?(?=\s|,|$)\s*", "корпус "),
    (r"\bстр\.?(?=\s|,|$)\s*", "строение "),
    (r"\bлит\.?(?=\s|,|$)\s*", "литера "),
]


SETTLEMENT_CONTEXT_MARKERS = (
    "петергоф",
    "ломоносов",
    "кронштадт",
    "сестрорецк",
    "зеленогорск",
    "красное село",
    "колпино",
    "пушкин",
    "павловск",
    "шушары",
    "парголово",
    "мурино",
    "кудрово",
    "всеволожск",
    "кириши",
    "гатчина",
    "тосно",
    "выборг",
    "нурма",
)


ADDRESS_MARKER_PATTERNS = [
    r"\bспб\b",
    r"\bс\.?\s*петербург\b",
    r"\bсанкт(?:[-\s]+петербург)?\b",
    r"\bпетербург\b",
    r"\bленинградская\s+область\b",
    r"\bлен(?:инградская)?\.?\s*обл\.?(?=\s|,|$)",
    r"\bленобласть\b",
    r"\bул\.?\b",
    r"\bулиц[аы]\b",
    r"\bпр-т\.?\b",
    r"\bпросп\.?\b",
    r"\bпр\.?\b",
    r"\bпроспект\b",
    r"\bнаб\.?\b",
    r"\bнабережная\b",
    r"\bпер\.?\b",
    r"\bпереулок\b",
    r"\bпл\.?\b",
    r"\bплощадь\b",
    r"\bш\.?\b",
    r"\bшоссе\b",
    r"\bб-р\.?\b",
    r"\bбул\.?\b",
    r"\bбульв\.?\b",
    r"\bбульвар\b",
    r"\bостров\b",
    r"\bд\.?\b",
    r"\bдом\b",
    r"\bкорп\.?\b",
    r"\bкорпус\b",
    r"\bк\.?\b",
    r"\bстр\.?\b",
    r"\bстроение\b",
    r"\bлит\.?\b",
    r"\bлитера\b",
    r"\bлиния\b",
] + [
    rf"\b{re.escape(marker)}\b"
    for marker in SETTLEMENT_CONTEXT_MARKERS
]


CITY_CONTEXT_MARKERS = [
    "санкт-петербург",
    "ленинградская область",
    *SETTLEMENT_CONTEXT_MARKERS,
]


def normalize_spaces(value: str) -> str:
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r",+", ",", value)
    return value.strip(" ,")


def normalize_house_suffixes(value: str) -> str:
    value = re.sub(r"(\d+)\s*a(?=$|[\s,])", r"\1а", value, flags=re.IGNORECASE)
    value = re.sub(r"(\d+)\s+([а-я])(?=$|[\s,])", r"\1\2", value, flags=re.IGNORECASE)
    return value


def clean_place_name(value: str | None) -> str | None:
    if value is None:
        return None

    value = normalize_spaces(value.strip(" :-—–|;,\t\n\r"))
    return value or None


def has_address_marker(value: str) -> bool:
    value = normalize_spaces(value.lower().replace("ё", "е"))
    return any(re.search(pattern, value) for pattern in ADDRESS_MARKER_PATTERNS)


def normalize_default_city(value: str) -> str:
    value = normalize_spaces(value.lower().replace("ё", "е"))

    for pattern, replacement in REPLACEMENTS:
        value = re.sub(pattern, replacement, value)

    return normalize_spaces(value)


def looks_like_address(value: str) -> bool:
    value = normalize_spaces(value.lower().replace("ё", "е"))

    if has_address_marker(value):
        return True

    return bool(re.search(r"\d", value))


def split_place_name_from_address(address: str) -> tuple[str | None, str]:
    value = normalize_spaces(
        address
        .replace("\r", "\n")
        .replace("\n", ",")
        .replace(";", ",")
        .replace("|", ",")
        .replace("\t", " ")
    )

    explicit_match = re.match(r"^(.+?)\s*(?::|—|–|\s-\s)\s*(.+)$", value)
    if explicit_match:
        possible_place = clean_place_name(explicit_match.group(1))
        possible_address = normalize_spaces(explicit_match.group(2))
        if (
            possible_place
            and possible_address
            and not has_address_marker(possible_place)
            and looks_like_address(possible_address)
        ):
            return possible_place, possible_address

    parts = [part.strip() for part in value.split(",") if part.strip()]
    if len(parts) < 2:
        return None, value

    possible_place = clean_place_name(parts[0])
    possible_address = normalize_spaces(", ".join(parts[1:]))

    if (
        possible_place
        and possible_address
        and not has_address_marker(possible_place)
        and looks_like_address(possible_address)
    ):
        return possible_place, possible_address

    return None, value


def normalize_address(
    address: str,
    default_city: str | None = "санкт-петербург",
    place_name: str | None = None,
) -> NormalizedAddress:
    if not address or not address.strip():
        raise ValueError("Address is empty")

    original = address.strip()
    explicit_place_name = clean_place_name(place_name)

    if explicit_place_name:
        detected_place_name = explicit_place_name
        address_for_geocoding = original
    else:
        detected_place_name, address_for_geocoding = split_place_name_from_address(original)

    value = address_for_geocoding.lower()
    value = value.replace("ё", "е")

    value = value.replace(";", ",")
    value = value.replace("|", ",")
    value = value.replace("\t", " ")

    value = normalize_spaces(value)
    value = re.sub(r"(?<=\d)\s*к\s*(?=\d)", " корпус ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<=\d)\s*корп\.?\s*(?=\d)", " корпус ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<=\d)\s*стр\.?\s*(?=\d)", " строение ", value, flags=re.IGNORECASE)
    value = re.sub(r"(?<=\d)\s*лит\.?\s*(?=[a-zа-я])", " литера ", value, flags=re.IGNORECASE)

    for pattern, replacement in REPLACEMENTS:
        value = re.sub(pattern, replacement, value)

    value = normalize_spaces(value)
    value = normalize_house_suffixes(value)

    has_city = any(city in value for city in CITY_CONTEXT_MARKERS)
    if default_city and not has_city:
        value = f"{normalize_default_city(default_city)}, {value}"

    value = normalize_spaces(value)
    value = normalize_house_suffixes(value)

    tokens = [
        token
        for token in re.split(r"[,\s]+", value)
        if token
    ]

    return NormalizedAddress(
        original_address=original,
        address_for_geocoding=address_for_geocoding,
        normalized_address=value,
        tokens=tokens,
        place_name=detected_place_name,
    )
