import re
from typing import List, Optional

from ..schemas.parsed_address import GeocodingQuery, ParsedAddress


_ABBREV_MAP = {
    r"\bул\.?\b": "улица",
    r"\bпр\.?\b": "проспект",
    r"\bпер\.?\b": "переулок",
    r"\bнаб\.?\b": "набережная",
    r"\bпл\.?\b": "площадь",
    r"\bд\.?\b": "д",
    r"\bк\.?\b": "к",
    r"\bстр\.?\b": "стр",
}


def _apply_abbrev_replacements(s: str) -> str:
    for pat, repl in _ABBREV_MAP.items():
        s = re.sub(pat, repl, s, flags=re.IGNORECASE)
    return s


def _extract_parts(s: str) -> dict:
    parts = {"street": None, "house": None, "building": None, "settlement": None}

    # House
    m = re.search(r"(?:\bд(?:ом)?\b|\bд\.?\b)\s*([\w\-/А-Яа-я]+)", s, flags=re.IGNORECASE)
    if m:
        parts["house"] = m.group(1)

    # Building / корпус / стр
    m = re.search(r"(?:\bк(?:орпус)?\b|\bк\.?\b|\bстр(?:оение)?\b|\bстр\.?\b)\s*([\w\-/А-Яа-я]+)", s, flags=re.IGNORECASE)
    if m:
        parts["building"] = m.group(1)

    # Try to capture street by looking for common street keywords
    m = re.search(r"(улица|проспект|переулок|набережная|площадь)\s+([\w\-\.А-Яа-я0-9 ]+?)(?:,|$|\sд\b|\sк\b|\sстр\b)", s, flags=re.IGNORECASE)
    if m:
        parts["street"] = m.group(2).strip()

    # Settlement hint (like "Санкт-Петербург", "Ленинградская область")
    if re.search(r"санкт-?петербург|спб|спб\b", s, flags=re.IGNORECASE):
        parts["settlement"] = "SPB"
    elif re.search(r"ленинградская|ленобл|лен\.обл\b", s, flags=re.IGNORECASE):
        parts["settlement"] = "LENOBL"

    return parts


def _build_queries(cleaned: str, parsed_parts: dict, region_hint: Optional[str]) -> List[GeocodingQuery]:
    queries: List[GeocodingQuery] = []

    # Highest priority: explicit region + full address
    if region_hint:
        queries.append(GeocodingQuery(query=f"{region_hint}, {cleaned}", priority=100, region_hint=region_hint, note="explicit_region"))

    # Settlement-specific
    settlement = parsed_parts.get("settlement")
    if settlement == "SPB":
        queries.append(GeocodingQuery(query=f"Санкт-Петербург, {cleaned}", priority=95, region_hint="SPB", note="spb_hint"))
        queries.append(GeocodingQuery(query=f"Ленинградская область, {cleaned}", priority=85, region_hint="LENOBL", note="lenobl_fallback"))
    elif settlement == "LENOBL":
        queries.append(GeocodingQuery(query=f"Ленинградская область, {cleaned}", priority=95, region_hint="LENOBL", note="lenobl_hint"))
        queries.append(GeocodingQuery(query=f"Санкт-Петербург, {cleaned}", priority=85, region_hint="SPB", note="spb_fallback"))
    else:
        queries.append(GeocodingQuery(query=cleaned, priority=80, note="bare"))
        queries.append(GeocodingQuery(query=f"Санкт-Петербург, {cleaned}", priority=70, region_hint="SPB", note="spb_try"))
        queries.append(GeocodingQuery(query=f"Ленинградская область, {cleaned}", priority=60, region_hint="LENOBL", note="lenobl_try"))

    # If there is a region hint and no explicit settlement, try adding it too
    if region_hint and not settlement:
        queries.insert(0, GeocodingQuery(query=f"{region_hint}, {cleaned}", priority=98, region_hint=region_hint, note="explicit_region_hint"))

    # If we have explicit street/house, add a focused query
    street = parsed_parts.get("street")
    house = parsed_parts.get("house")
    if street and house:
        focused = f"{street} {house}"
        if region_hint:
            queries.insert(0, GeocodingQuery(query=f"{region_hint}, {focused}", priority=110, region_hint=region_hint, note="focused_with_region"))
        else:
            queries.insert(0, GeocodingQuery(query=focused, priority=105, note="focused"))

    # Deduplicate preserving order
    seen = set()
    out: List[GeocodingQuery] = []
    for q in queries:
        if q.query not in seen:
            out.append(q)
            seen.add(q.query)

    return out


def normalize_address(raw_address: str, region_hint: Optional[str] = None) -> ParsedAddress:
    """Normalize a freeform address into a ParsedAddress with several candidate queries.

    This implementation is intentionally conservative and deterministic — it produces
    a small ranked list of geocoding query variants that callers can try in order.
    """
    original = raw_address or ""
    s = original.strip()
    s = re.sub(r"[,:]+", " ", s)
    s = re.sub(r"\s+", " ", s)

    s = _apply_abbrev_replacements(s)

    parts = _extract_parts(s)

    normalized_key = f"{parts.get('settlement') or ''}|{parts.get('street') or ''}|{parts.get('house') or ''}|{parts.get('building') or ''}".strip("|")

    queries = _build_queries(s, parts, region_hint)

    return ParsedAddress(
        original=original,
        cleaned=s,
        normalized_key=normalized_key,
        region_hint=region_hint,
        settlement_hint=parts.get("settlement"),
        street=parts.get("street"),
        house=parts.get("house"),
        building=parts.get("building"),
        geocoding_queries=queries,
    )
