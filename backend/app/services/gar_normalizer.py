from __future__ import annotations

import re
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.gar import GarAddressVariant, GarNormalizeResult
from app.services.address_normalizer import normalize_address as parse_address
from app.services.gar_importer import REGION_LABELS, normalize_region_codes


STREET_TYPE_WORDS = {
    "улица",
    "ул",
    "проспект",
    "пр",
    "переулок",
    "пер",
    "набережная",
    "наб",
    "площадь",
    "пл",
    "шоссе",
    "ш",
    "бульвар",
    "бул",
    "проезд",
    "линия",
}


def normalize_lookup_text(value: str | None) -> str:
    value = (value or "").lower().replace("ё", "е")
    value = re.sub(r"[.,;|]+", " ", value)
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def street_name_without_type(value: str | None) -> str:
    tokens = [
        token
        for token in re.split(r"\s+", normalize_lookup_text(value))
        if token and token not in STREET_TYPE_WORDS
    ]
    return " ".join(tokens)


def normalize_house_value(value: str | None) -> str:
    value = normalize_lookup_text(value)
    value = re.sub(r"\b(?:дом|д)\s*", "", value)
    value = re.sub(r"\b(?:корпус|корп|к)\s*", "к", value)
    value = re.sub(r"\b(?:строение|стр)\s*", "с", value)
    value = re.sub(r"\s+", "", value)
    return value


def house_display(row: dict[str, Any]) -> str | None:
    house = row.get("house_number")
    if not house:
        return None

    parts = [str(house)]
    if row.get("building_number"):
        parts.append(f"корп {row['building_number']}")
    if row.get("structure_number"):
        parts.append(f"стр {row['structure_number']}")
    return " ".join(parts)


def region_label(region_code: str | None) -> str | None:
    if not region_code:
        return None
    return REGION_LABELS.get(region_code, (region_code, None))[0]


def normalized_full_address(
    *,
    street_row: dict[str, Any],
    house_row: dict[str, Any] | None,
    settlement: str | None = None,
) -> str:
    parts = []
    region = region_label(street_row.get("region_code"))
    if region:
        parts.append(region)
    if settlement and settlement.lower() not in {part.lower() for part in parts}:
        parts.append(settlement)
    parts.append(street_row["full_name"])

    if house_row is not None:
        house = house_display(house_row)
        if house:
            parts.append(f"д {house}")

    return ", ".join(part for part in parts if part)


class GarAddressNormalizer:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def normalize(
        self,
        raw_address: str,
        *,
        region_hint: str | None = None,
        city_hint: str | None = None,
    ) -> GarNormalizeResult:
        parsed = parse_address(raw_address, region_hint=region_hint)
        street = parsed.street
        house = parsed.house
        settlement = city_hint or parsed.settlement_hint
        region_codes = normalize_region_codes(region_hint)

        if not street:
            return GarNormalizeResult(
                status="not_found",
                normalized_full_address=parsed.normalized_address,
                confidence=0.0,
                comment="Street was not detected in the input address.",
            )

        street_rows = await self._find_streets(
            street=street,
            settlement=settlement,
            region_codes=region_codes,
        )
        if not street_rows:
            return GarNormalizeResult(
                status="not_found",
                normalized_full_address=parsed.normalized_address,
                street=street,
                house=house,
                confidence=0.0,
                comment="Street was not found in GAR/FIAS.",
            )

        if not house:
            variants = [
                self._variant(street_row=row, house_row=None, settlement=settlement, confidence=0.72)
                for row in street_rows[:5]
            ]
            if len(variants) > 1:
                return GarNormalizeResult(
                    status="ambiguous",
                    normalized_full_address=variants[0].normalized_full_address,
                    region=variants[0].region,
                    street=street,
                    confidence=0.6,
                    comment="Several matching streets were found; house number is missing.",
                    variants=variants,
                )
            return GarNormalizeResult(
                status="partial_match",
                normalized_full_address=variants[0].normalized_full_address,
                region=variants[0].region,
                city=variants[0].city,
                settlement=variants[0].settlement,
                street=variants[0].street,
                gar_object_id=variants[0].gar_object_id,
                fias_id=variants[0].fias_id,
                confidence=0.72,
                comment="Street was found, but house number is missing.",
                variants=variants,
            )

        house_variants: list[GarAddressVariant] = []
        partial_variants: list[GarAddressVariant] = []
        for street_row in street_rows:
            house_rows = await self._find_houses(street_row, house=house, corpus=parsed.corpus)
            if not house_rows:
                partial_variants.append(
                    self._variant(
                        street_row=street_row,
                        house_row=None,
                        settlement=settlement,
                        confidence=0.64,
                    )
                )
                continue

            for house_row in house_rows:
                house_variants.append(
                    self._variant(
                        street_row=street_row,
                        house_row=house_row,
                        settlement=settlement,
                        confidence=0.97,
                    )
                )

        if len(house_variants) == 1:
            variant = house_variants[0]
            return GarNormalizeResult(
                status="exact_match",
                normalized_full_address=variant.normalized_full_address,
                region=variant.region,
                city=variant.city,
                settlement=variant.settlement,
                street=variant.street,
                house=variant.house,
                building=variant.building,
                structure=variant.structure,
                postcode=variant.postcode,
                gar_object_id=variant.gar_object_id,
                gar_house_id=variant.gar_house_id,
                fias_id=variant.fias_id,
                confidence=variant.confidence,
                variants=house_variants,
            )

        if len(house_variants) > 1:
            return GarNormalizeResult(
                status="ambiguous",
                normalized_full_address=house_variants[0].normalized_full_address,
                region=house_variants[0].region,
                street=street,
                house=house,
                confidence=0.74,
                comment="Several matching GAR/FIAS houses were found.",
                variants=house_variants[:10],
            )

        return GarNormalizeResult(
            status="partial_match",
            normalized_full_address=partial_variants[0].normalized_full_address if partial_variants else None,
            region=partial_variants[0].region if partial_variants else None,
            street=street,
            house=house,
            confidence=0.55,
            comment="Street was found in GAR/FIAS, but house was not found.",
            variants=partial_variants[:10],
        )

    async def _find_streets(
        self,
        *,
        street: str,
        settlement: str | None,
        region_codes: list[str],
    ) -> list[dict[str, Any]]:
        street_lookup = normalize_lookup_text(street)
        street_name = street_name_without_type(street)
        like = f"%{street_name or street_lookup}%"
        settlement_like = f"%{normalize_lookup_text(settlement)}%" if settlement else None

        result = await self.db.execute(
            text(
                """
                SELECT
                    id,
                    gar_id,
                    object_id,
                    parent_object_id,
                    object_level,
                    name,
                    type_name,
                    full_name,
                    region_code,
                    path,
                    GREATEST(
                        similarity(lower(full_name), :street_lookup),
                        similarity(lower(name), :street_name)
                    ) AS score
                FROM gar_address_objects
                WHERE is_actual = TRUE
                  AND is_active = TRUE
                  AND (:region_codes_empty OR region_code = ANY(CAST(:region_codes AS text[])))
                  AND (
                    CAST(:settlement_like AS text) IS NULL
                    OR lower(coalesce(path, '') || ' ' || full_name) LIKE CAST(:settlement_like AS text)
                  )
                  AND (
                    lower(full_name) = :street_lookup
                    OR lower(name) = :street_name
                    OR lower(full_name) LIKE :like
                    OR lower(name) LIKE :like
                    OR similarity(lower(full_name), :street_lookup) > 0.25
                    OR similarity(lower(name), :street_name) > 0.25
                  )
                ORDER BY
                    CASE
                        WHEN lower(full_name) = :street_lookup OR lower(name) = :street_name THEN 0
                        ELSE 1
                    END,
                    score DESC,
                    object_level DESC NULLS LAST
                LIMIT 10
                """
            ),
            {
                "street_lookup": street_lookup,
                "street_name": street_name,
                "like": like,
                "settlement_like": settlement_like,
                "region_codes": region_codes,
                "region_codes_empty": not bool(region_codes),
            },
        )
        return [dict(row) for row in result.mappings().all()]

    async def _find_houses(
        self,
        street_row: dict[str, Any],
        *,
        house: str,
        corpus: str | None,
    ) -> list[dict[str, Any]]:
        house_lookup = normalize_house_value(house)
        house_with_corpus = normalize_house_value(
            f"{house} корпус {corpus}" if corpus else house
        )

        result = await self.db.execute(
            text(
                """
                SELECT
                    id,
                    gar_id,
                    object_id,
                    house_id,
                    parent_object_id,
                    house_number,
                    building_number,
                    structure_number,
                    house_type,
                    building_type,
                    structure_type,
                    postcode,
                    region_code
                FROM gar_houses
                WHERE is_actual = TRUE
                  AND is_active = TRUE
                  AND parent_object_id = :street_object_id
                  AND (
                    regexp_replace(lower(coalesce(house_number, '')), '\\s+', '', 'g') = :house_lookup
                    OR regexp_replace(lower(concat_ws('', house_number, 'к', building_number)), '\\s+', '', 'g') = :house_with_corpus
                    OR regexp_replace(lower(concat_ws('', house_number, building_number)), '\\s+', '', 'g') = :house_with_corpus
                  )
                ORDER BY
                    CASE
                        WHEN regexp_replace(lower(coalesce(house_number, '')), '\\s+', '', 'g') = :house_lookup THEN 0
                        ELSE 1
                    END,
                    id
                LIMIT 10
                """
            ),
            {
                "street_object_id": street_row["object_id"],
                "house_lookup": house_lookup,
                "house_with_corpus": house_with_corpus,
            },
        )
        return [dict(row) for row in result.mappings().all()]

    def _variant(
        self,
        *,
        street_row: dict[str, Any],
        house_row: dict[str, Any] | None,
        settlement: str | None,
        confidence: float,
    ) -> GarAddressVariant:
        region = region_label(street_row.get("region_code"))
        house = house_display(house_row) if house_row is not None else None
        return GarAddressVariant(
            normalized_full_address=normalized_full_address(
                street_row=street_row,
                house_row=house_row,
                settlement=settlement,
            ),
            region=region,
            city="Санкт-Петербург" if street_row.get("region_code") == "78" else None,
            settlement=settlement,
            street=street_row["full_name"],
            house=house,
            building=house_row.get("building_number") if house_row is not None else None,
            structure=house_row.get("structure_number") if house_row is not None else None,
            postcode=house_row.get("postcode") if house_row is not None else None,
            gar_object_id=street_row["id"],
            gar_house_id=house_row.get("id") if house_row is not None else None,
            fias_id=(
                house_row.get("gar_id")
                if house_row is not None and house_row.get("gar_id")
                else street_row.get("gar_id")
            ),
            confidence=confidence,
        )
