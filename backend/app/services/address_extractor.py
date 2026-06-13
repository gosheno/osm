from __future__ import annotations

import re
from dataclasses import dataclass


STORE_NAMES = (
    "Агроторг",
    "Перекресток",
    "Пятерочка",
    "Семишагофф",
    "Магнит",
    "Дикси",
    "Лента",
    "Окей",
)

SETTLEMENT_WORDS = (
    "Санкт-Петербург",
    "СПб",
    "Коммунар",
    "Гатчина",
    "Вырица",
    "Луга",
    "Сиверский",
    "Мшинская",
    "Пудомяги",
    "Белогорка",
    "Мины",
    "Дружная Горка",
    "Семрино",
    "Сусанино",
    "Форносово",
)

STREET_PATTERN = re.compile(
    r"(?P<address>"
    r"(?:(?:г\.?\s*)?(?:Санкт[-\s]?Петербург|СПб|"
    r"Коммунар|Гатчина|Вырица|Луга|Сиверский|Мшинская|Пудомяги|"
    r"Белогорка|Мины|Дружная\s+Горка|Семрино|Сусанино|Форносово)\s*,?\s*)?"
    r"[А-Яа-яЁё0-9\-\s.]+?\s+"
    r"(?:ул\.?|улица|пр\.?|проспект|ш\.?|шоссе|пер\.?|переулок|"
    r"пл\.?|площадь|наб\.?|набережная|б-р|бульвар|линия|пр-д|проезд)"
    r"[А-Яа-яЁё0-9\-\s.,/]*"
    r"(?:,\s*)?(?:д\.?\s*)?\d+[0-9А-Яа-яA-Za-z/\-]*(?:\s*(?:к|корп\.?|лит\.?|стр\.?)\s*[0-9А-Яа-яA-Za-z/\-]+)?"
    r")",
    flags=re.IGNORECASE,
)

HOUSE_ONLY_PATTERN = re.compile(
    r"(?P<address>"
    r"(?:Пудомяги|Сусанино|Форносово|Белогорка|Мины|Семрино)\s*,?\s*"
    r"(?:д\.?\s*)?\d+[0-9А-Яа-яA-Za-z/\-]*"
    r")",
    flags=re.IGNORECASE,
)

NOISE_PATTERN = re.compile(
    r"\b(?:дата|панорам|адрес|склад|документы|поставил|возврат|офис|тел|телефон)\b",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class ExtractedAddress:
    raw_text: str
    store_name: str | None
    address: str
    confidence_score: float


def clean_ocr_text(value: str) -> str:
    value = (value or "").replace("|", " ").replace("—", "-")
    value = _fix_common_ocr_address_tokens(value)
    value = re.sub(r"\s+", " ", value)
    value = re.sub(r"\s*,\s*", ", ", value)
    return value.strip(" ,")


def _fix_common_ocr_address_tokens(value: str) -> str:
    replacements = (
        (r"\b(?:yn|yA|yx|ya)\.?\b", "ул."),
        (r"\b(?:np|pr)\.?\b", "пр."),
        (r"\bуп\.?\b", "ул."),
        (r"\bУп\.?\b", "ул."),
        (r"\bПуга\b", "Луга"),
        (r"\bNyra\b", "Луга"),
        (r"\bnyra\b", "Луга"),
        (r"\bМимы\b", "Мины"),
        (r"\bДружмая\b", "Дружная"),
        (r"\bЖепезнодорожмая\b", "Железнодорожная"),
        (r"\bСтронктелей\b", "Строителей"),
        (r"\bСтроктелей\b", "Строителей"),
        (r"\bГ\s+ороев\b", "Героев"),
        (r"\bГероее\b", "Героев"),
        (r"\bСоболовского\b", "Соболевского"),
        (r"\bСоболеоского\b", "Соболевского"),
        (r"\bГатчинска\s+ул\b", "Гатчинская ул"),
        (r"\bХвалыиская\b", "Хвалынская"),
        (r"\bсусаниио\b", "Сусанино"),
        (r"\bоммунар\b", "Коммунар"),
        (r"\bУрицкого\s+пр\.?\s*713\b", "Урицкого пр. 77/3"),
        (r"\bУрицкого\s+пр[-.\s]+73\b", "Урицкого пр. 77/3"),
    )
    fixed = value
    for pattern, replacement in replacements:
        fixed = re.sub(pattern, replacement, fixed, flags=re.IGNORECASE)
    return fixed


def extract_delivery_record(line: str, previous_line: str | None = None) -> ExtractedAddress | None:
    cleaned = clean_ocr_text(line)
    if not cleaned or NOISE_PATTERN.search(cleaned):
        return None

    match = STREET_PATTERN.search(cleaned) or HOUSE_ONLY_PATTERN.search(cleaned)
    if not match:
        return None

    address = _clean_address_candidate(match.group("address"))
    if not _has_house_number(address):
        return None

    store_name = _extract_store_name(cleaned) or _extract_store_name(previous_line or "")
    confidence = _confidence(cleaned, address, store_name)
    return ExtractedAddress(
        raw_text=cleaned,
        store_name=store_name,
        address=address,
        confidence_score=confidence,
    )


def _extract_store_name(value: str) -> str | None:
    normalized = clean_ocr_text(value)
    for store in STORE_NAMES:
        if re.search(re.escape(store), normalized, flags=re.IGNORECASE):
            return store
    return None


def _clean_address_candidate(value: str) -> str:
    cleaned = clean_ocr_text(value)
    for store in STORE_NAMES:
        cleaned = re.sub(re.escape(store), " ", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{4,}\b", " ", cleaned)
    cleaned = re.sub(r"^\s*\d{1,3}\s+\d{1,3}\s+", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    cleaned = re.sub(r"\s*,\s*", ", ", cleaned)
    cleaned = _trim_after_first_house_number(cleaned)
    return cleaned.strip(" ,")


def _trim_after_first_house_number(value: str) -> str:
    street_type = (
        r"ул\.?|улица|пр\.?|проспект|ш\.?|шоссе|пер\.?|переулок|"
        r"пл\.?|площадь|наб\.?|набережная|б-р|бульвар|линия|пр-д|проезд"
    )
    match = re.search(
        rf"^(.+?\b(?:{street_type})\.?\s*,?\s*(?:д\.?\s*)?"
        rf"\d+[0-9А-Яа-яA-Za-z/\-]*"
        rf"(?:\s*(?:к|корп\.?|лит\.?|стр\.?)\s*[0-9А-Яа-яA-Za-z/\-]+)?)",
        value,
        flags=re.IGNORECASE,
    )
    return match.group(1) if match else value


def _has_house_number(address: str) -> bool:
    return bool(re.search(r"\d+[0-9А-Яа-яA-Za-z/\-]*\s*$", address.strip()))


def _confidence(raw_text: str, address: str, store_name: str | None) -> float:
    score = 0.45
    if store_name:
        score += 0.12
    if any(word.lower() in address.lower() for word in SETTLEMENT_WORDS):
        score += 0.12
    if re.search(r"(ул|улица|пр|проспект|ш|шоссе|наб|набережная|линия)", address, re.I):
        score += 0.14
    if _has_house_number(address):
        score += 0.12
    if len(raw_text) < 12:
        score -= 0.2
    return round(max(0.0, min(score, 0.99)), 2)
