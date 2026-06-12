import re

from app.schemas.parsed_address import GeocodingQuery, ParsedAddress
from app.services.geocoding_context import (
    GeocodingContext,
    LENOBL_LABEL,
    LENOBL_SETTLEMENTS,
    SPB_ALIASES,
    SPB_LABEL,
    SPB_SETTLEMENTS,
    normalize_context_label,
)


STREET_TYPES = (
    "улица",
    "проспект",
    "переулок",
    "набережная",
    "площадь",
    "шоссе",
    "бульвар",
    "линия",
)

ABBREVIATIONS = [
    (r"\bул\.?(?=\s|,|$)\s*", "улица "),
    (r"\bпр-т\.?(?=\s|,|$)\s*", "проспект "),
    (r"\bпросп\.?(?=\s|,|$)\s*", "проспект "),
    (r"\bпр\.?(?=\s|,|$)\s*", "проспект "),
    (r"\bпер\.?(?=\s|,|$)\s*", "переулок "),
    (r"\bнаб\.?(?=\s|,|$)\s*", "набережная "),
    (r"\bпл\.?(?=\s|,|$)\s*", "площадь "),
    (r"\bш\.?(?=\s|,|$)\s*", "шоссе "),
    (r"\bб-р\.?(?=\s|,|$)\s*", "бульвар "),
    (r"\bбул\.?(?=\s|,|$)\s*", "бульвар "),
    (r"\bд\.?(?=\s|,|$)\s*", "дом "),
    (r"\bк\.?(?=\s|,|$)\s*", "корпус "),
    (r"\bкорп\.?(?=\s|,|$)\s*", "корпус "),
    (r"\bстр\.?(?=\s|,|$)\s*", "строение "),
    (r"\bлит\.?(?=\s|,|$)\s*", "литера "),
]


def _clean(value: str) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = value.replace(";", ",").replace("|", ",").replace("\t", " ")
    value = re.sub(r"\s*,\s*", ", ", value)
    value = re.sub(r"\s+", " ", value)
    value = value.strip(" ,")

    for pattern, replacement in ABBREVIATIONS:
        value = re.sub(pattern, replacement, value, flags=re.IGNORECASE)

    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    return value.strip(" ,")


def _contains_any(value: str, items: set[str]) -> str | None:
    normalized = normalize_context_label(value)
    for item in sorted(items, key=len, reverse=True):
        if re.search(rf"(^|\s|,){re.escape(item)}($|\s|,)", normalized):
            return item
    return None


def _extract_region(cleaned: str) -> str | None:
    normalized = normalize_context_label(cleaned)
    if _contains_any(normalized, SPB_ALIASES):
        return SPB_LABEL
    if re.search(r"\b(ленинградская область|ленобласть|лен обл)\b", normalized):
        return LENOBL_LABEL
    if _contains_any(normalized, set(SPB_SETTLEMENTS)):
        return SPB_LABEL
    if _contains_any(normalized, set(LENOBL_SETTLEMENTS)):
        return LENOBL_LABEL
    return None


def _extract_settlement(cleaned: str) -> str | None:
    normalized = normalize_context_label(cleaned)
    return (
        _contains_any(normalized, set(SPB_SETTLEMENTS))
        or _contains_any(normalized, set(LENOBL_SETTLEMENTS))
    )


def _strip_region_prefix(cleaned: str) -> str:
    value = cleaned
    prefixes = [
        "санкт-петербург",
        "санкт петербург",
        "спб",
        "петербург",
        "ленинградская область",
        "ленобласть",
    ]
    for prefix in prefixes:
        value = re.sub(rf"^{re.escape(prefix)}\s*,?\s*", "", value, flags=re.IGNORECASE)
    return value.strip(" ,")


def _strip_settlement_prefix(cleaned: str, settlement: str | None) -> str:
    value = _strip_region_prefix(cleaned)
    if settlement:
        value = re.sub(rf"^{re.escape(settlement)}\s*,?\s*", "", value, flags=re.IGNORECASE)
        value = _strip_region_prefix(value)
    return value.strip(" ,")


def _extract_house(cleaned: str) -> str | None:
    match = re.search(r"\b(?:дом|д)\s*([0-9]+[0-9а-яa-z/-]*)", cleaned, flags=re.IGNORECASE)
    if match:
        return match.group(1)

    match = re.search(r"([0-9]+[0-9а-яa-z/-]*)\s*$", cleaned, flags=re.IGNORECASE)
    return match.group(1) if match else None


def _extract_named_part(cleaned: str, labels: tuple[str, ...]) -> str | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(
        rf"\b(?:{label_pattern})\s*([0-9]+[0-9а-яa-z/-]*)",
        cleaned,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else None


def _extract_street(cleaned: str) -> str | None:
    street_type_pattern = "|".join(re.escape(item) for item in STREET_TYPES)

    match = re.search(
        rf"\b({street_type_pattern})\s+(.+?)(?:\s+дом\b|\s+корпус\b|\s+строение\b|\s+литера\b|,|$)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)} {match.group(2)}".strip()

    match = re.search(
        rf"(.+?)\s+({street_type_pattern})(?:\s+дом\b|\s+корпус\b|\s+строение\b|\s+литера\b|,|$)",
        cleaned,
        flags=re.IGNORECASE,
    )
    if match:
        return f"{match.group(1)} {match.group(2)}".strip()

    no_region = _strip_region_prefix(cleaned)
    no_house = re.sub(r"\bдом\s*[0-9]+[0-9а-яa-z/-]*", "", no_region, flags=re.IGNORECASE)
    no_house = re.sub(r"[0-9]+[0-9а-яa-z/-]*\s*$", "", no_house, flags=re.IGNORECASE)
    no_house = re.sub(r"\b(корпус|строение|литера)\s+\S+", "", no_house, flags=re.IGNORECASE)
    no_house = no_house.strip(" ,")
    return no_house or None


def _normalized_key(
    *,
    region: str | None,
    settlement: str | None,
    street: str | None,
    house: str | None,
    corpus: str | None,
    building: str | None,
    letter: str | None,
) -> str:
    values = [region, settlement, street, house, corpus, building, letter]
    return "|".join(value for value in values if value)


def _query_parts(cleaned: str, settlement: str | None) -> tuple[str, str]:
    without_region = _strip_region_prefix(cleaned)
    without_settlement = _strip_settlement_prefix(cleaned, settlement)
    return without_region, without_settlement


def _has_street_type(value: str) -> bool:
    return any(
        re.search(rf"(^|\s){re.escape(street_type)}($|\s)", value)
        for street_type in STREET_TYPES
    )


def _street_without_type(value: str) -> str:
    street = value.strip(" ,")
    for street_type in STREET_TYPES:
        street = re.sub(
            rf"^{re.escape(street_type)}\s+",
            "",
            street,
            flags=re.IGNORECASE,
        )
        street = re.sub(
            rf"\s+{re.escape(street_type)}$",
            "",
            street,
            flags=re.IGNORECASE,
        )
    return street.strip(" ,")


def _street_type_guesses(street: str) -> list[str]:
    if street.endswith("ское"):
        return ["шоссе"]
    if street.endswith("ский"):
        return ["проспект", "улица"]
    return ["улица"]


def _local_query_variants(base: str, street: str | None, house: str | None) -> list[str]:
    variants: list[str] = []

    if street and house:
        street_name = _street_without_type(street)
        if street_name and not _has_street_type(street):
            for street_type in _street_type_guesses(street_name):
                variants.append(f"{street_type} {street_name} {house}")
                variants.append(f"{street_name} {street_type} {house}")

    variants.append(base)

    deduplicated: list[str] = []
    for variant in variants:
        variant = re.sub(r"\s+", " ", variant).strip(" ,")
        if variant and variant not in deduplicated:
            deduplicated.append(variant)
    return deduplicated


def _add_query(
    queries: list[GeocodingQuery],
    query: str,
    *,
    priority: int,
    region_hint: str | None = None,
    settlement_hint: str | None = None,
    note: str | None = None,
) -> None:
    query = re.sub(r"\s+", " ", query).strip(" ,")
    if not query:
        return
    if any(existing.query == query for existing in queries):
        return
    queries.append(
        GeocodingQuery(
            query=query,
            priority=priority,
            region_hint=region_hint,
            settlement_hint=settlement_hint,
            note=note,
        )
    )


def _region_for_context(context: GeocodingContext | None) -> str | None:
    if context is None:
        return None

    normalized = normalize_context_label(context.label)
    if any(alias in normalized for alias in SPB_ALIASES):
        return SPB_LABEL
    if "ленинград" in normalized:
        return LENOBL_LABEL
    if _contains_any(normalized, set(SPB_SETTLEMENTS)):
        return SPB_LABEL
    if _contains_any(normalized, set(LENOBL_SETTLEMENTS)):
        return LENOBL_LABEL
    return None


def _is_area_constrained_context(context: GeocodingContext | None) -> bool:
    return bool(context and context.type in {"district", "custom_area"})


def _build_queries(
    cleaned: str,
    *,
    region: str | None,
    settlement: str | None,
    street: str | None,
    house: str | None,
    context: GeocodingContext | None,
) -> list[GeocodingQuery]:
    queries: list[GeocodingQuery] = []
    without_region, without_settlement = _query_parts(cleaned, settlement)

    if _is_area_constrained_context(context):
        context_settlement = normalize_context_label(context.label if context else None)
        if settlement and settlement == context_settlement and not without_settlement:
            base = settlement
        else:
            base = without_settlement or without_region or cleaned

        for index, query in enumerate(_local_query_variants(base, street, house)):
            _add_query(
                queries,
                query,
                priority=130 - index,
                region_hint=region,
                settlement_hint=settlement or context_settlement or None,
                note="area_viewbox",
            )

        return sorted(queries, key=lambda item: item.priority, reverse=True)

    if settlement in SPB_SETTLEMENTS:
        _add_query(
            queries,
            f"{SPB_LABEL}, {settlement}, {without_settlement}",
            priority=120,
            region_hint=SPB_LABEL,
            settlement_hint=settlement,
            note="spb_settlement",
        )
        _add_query(
            queries,
            f"{settlement}, {without_settlement}, {SPB_LABEL}",
            priority=115,
            region_hint=SPB_LABEL,
            settlement_hint=settlement,
            note="spb_settlement_suffix",
        )
    elif settlement in LENOBL_SETTLEMENTS:
        _add_query(
            queries,
            f"{LENOBL_LABEL}, {settlement}, {without_settlement}",
            priority=120,
            region_hint=LENOBL_LABEL,
            settlement_hint=settlement,
            note="lenobl_settlement",
        )
        _add_query(
            queries,
            f"{settlement}, {without_settlement}, {LENOBL_LABEL}",
            priority=115,
            region_hint=LENOBL_LABEL,
            settlement_hint=settlement,
            note="lenobl_settlement_suffix",
        )
    elif region == SPB_LABEL:
        _add_query(
            queries,
            f"{SPB_LABEL}, {without_region}",
            priority=110,
            region_hint=SPB_LABEL,
            note="explicit_spb",
        )
        _add_query(
            queries,
            f"{without_region}, {SPB_LABEL}",
            priority=105,
            region_hint=SPB_LABEL,
            note="explicit_spb_suffix",
        )
    elif region == LENOBL_LABEL:
        _add_query(
            queries,
            f"{LENOBL_LABEL}, {without_region}",
            priority=110,
            region_hint=LENOBL_LABEL,
            note="explicit_lenobl",
        )
        _add_query(
            queries,
            f"{without_region}, {LENOBL_LABEL}",
            priority=105,
            region_hint=LENOBL_LABEL,
            note="explicit_lenobl_suffix",
        )

    context_region = _region_for_context(context)
    if context and context.label and context.type not in {"default_spb", "spb_lenobl"}:
        context_label = context.label
        if context_region == LENOBL_LABEL:
            _add_query(
                queries,
                f"{LENOBL_LABEL}, {context_label}, {without_region}",
                priority=100,
                region_hint=LENOBL_LABEL,
                settlement_hint=context_label,
                note="context_lenobl",
            )
            _add_query(
                queries,
                f"{context_label}, {without_region}, {LENOBL_LABEL}",
                priority=95,
                region_hint=LENOBL_LABEL,
                settlement_hint=context_label,
                note="context_lenobl_suffix",
            )
        elif context_region == SPB_LABEL:
            _add_query(
                queries,
                f"{SPB_LABEL}, {context_label}, {without_region}",
                priority=100,
                region_hint=SPB_LABEL,
                settlement_hint=context_label,
                note="context_spb",
            )
            _add_query(
                queries,
                f"{context_label}, {without_region}, {SPB_LABEL}",
                priority=95,
                region_hint=SPB_LABEL,
                settlement_hint=context_label,
                note="context_spb_suffix",
            )
        else:
            _add_query(
                queries,
                f"{context_label}, {without_region}",
                priority=90,
                settlement_hint=context_label,
                note="context_label",
            )

    if not queries or (context and context.type == "spb_lenobl"):
        _add_query(
            queries,
            f"{SPB_LABEL}, {without_region}",
            priority=80,
            region_hint=SPB_LABEL,
            note="default_spb",
        )
        _add_query(
            queries,
            f"{without_region}, {SPB_LABEL}",
            priority=75,
            region_hint=SPB_LABEL,
            note="default_spb_suffix",
        )
        _add_query(
            queries,
            f"{LENOBL_LABEL}, {without_region}",
            priority=70,
            region_hint=LENOBL_LABEL,
            note="lenobl_fallback",
        )

    _add_query(queries, cleaned, priority=10, region_hint=region, settlement_hint=settlement, note="raw")

    return sorted(queries, key=lambda item: item.priority, reverse=True)


def normalize_address(
    raw_address: str,
    region_hint: str | None = None,
    context: GeocodingContext | None = None,
    place_name: str | None = None,
) -> ParsedAddress:
    original = raw_address or ""
    cleaned = _clean(original)
    region = region_hint or _extract_region(cleaned)
    settlement = _extract_settlement(cleaned)
    street = _extract_street(cleaned)
    house = _extract_house(cleaned)
    corpus = _extract_named_part(cleaned, ("корпус",))
    building = _extract_named_part(cleaned, ("строение",))
    letter = _extract_named_part(cleaned, ("литера",))

    normalized_key = _normalized_key(
        region=region,
        settlement=settlement,
        street=street,
        house=house,
        corpus=corpus,
        building=building,
        letter=letter,
    )

    queries = _build_queries(
        cleaned,
        region=region,
        settlement=settlement,
        street=street,
        house=house,
        context=context,
    )

    return ParsedAddress(
        original_address=original,
        place_name=place_name,
        cleaned_address=cleaned,
        normalized_address=cleaned,
        normalized_key=normalized_key,
        region_hint=region,
        settlement_hint=settlement,
        street=street,
        house=house,
        building=building,
        corpus=corpus,
        letter=letter,
        geocoding_queries=queries,
    )
