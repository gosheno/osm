from __future__ import annotations

from dataclasses import dataclass
from difflib import SequenceMatcher
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.poi_import.brand_normalizer import BrandAliasMatcher, normalize_brand_text
from app.services.poi_import.config import load_poi_config
from app.utils.address_normalizer import normalize_address


@dataclass(frozen=True)
class PoiCandidate:
    id: int
    canonical_brand: str
    name: str | None
    address: str | None
    normalized_address: str | None
    latitude: float
    longitude: float
    confidence_score: float | None
    distance_m: float | None
    osm_type: str | None
    osm_id: int | None
    score: float


@dataclass(frozen=True)
class PoiResolutionResult:
    status: str
    matched: PoiCandidate | None
    candidates: list[PoiCandidate]


class PoiMatcher:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.config = load_poi_config()
        self.alias_matcher = BrandAliasMatcher(self.config.chains)

    def detect_brand(self, text_value: str) -> str | None:
        match = self.alias_matcher.detect(text_value)
        return match.canonical_brand if match else None

    async def find_candidates(
        self,
        text_value: str,
        brand: str | None = None,
        lat: float | None = None,
        lon: float | None = None,
        radius_m: int | None = None,
        limit: int = 10,
    ) -> list[PoiCandidate]:
        clean_text = " ".join((text_value or "").split())
        detected_brand = self.detect_brand(brand) if brand else self.detect_brand(clean_text)
        if brand and not detected_brand:
            detected_brand = brand
        if not detected_brand and not clean_text:
            return []

        normalized_text = _normalize_query(clean_text)
        rows = await self._query_rows(
            q=clean_text,
            normalized_q=normalized_text,
            brand=detected_brand,
            lat=lat,
            lon=lon,
            radius_m=radius_m,
            limit=max(1, min(limit, 50)),
        )
        candidates = [
            self._candidate_from_row(row, normalized_text=normalized_text, lat=lat, lon=lon)
            for row in rows
        ]
        candidates.sort(key=lambda item: item.score, reverse=True)
        return candidates[:limit]

    async def resolve_or_return_candidates(self, text_value: str) -> PoiResolutionResult:
        candidates = await self.find_candidates(text_value, limit=5)
        if not candidates:
            return PoiResolutionResult(status="not_found", matched=None, candidates=[])
        best = candidates[0]
        second = candidates[1] if len(candidates) > 1 else None
        if best.score >= 0.86 and (second is None or best.score - second.score >= 0.08):
            return PoiResolutionResult(status="matched", matched=best, candidates=candidates)
        return PoiResolutionResult(status="ambiguous", matched=None, candidates=candidates)

    async def _query_rows(
        self,
        *,
        q: str,
        normalized_q: str,
        brand: str | None,
        lat: float | None,
        lon: float | None,
        radius_m: int | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        clauses = ["is_active = true", "is_duplicate = false"]
        params: dict[str, Any] = {"limit": limit * 4, "q_like": f"%{q}%", "normalized_like": f"%{normalized_q}%"}
        if brand:
            clauses.append("canonical_brand = :brand")
            params["brand"] = brand
        if q:
            clauses.append(
                """
                (
                    normalized_address ILIKE :normalized_like
                    OR original_address ILIKE :q_like
                    OR name ILIKE :q_like
                    OR detected_brand ILIKE :q_like
                    OR canonical_brand ILIKE :q_like
                )
                """
            )
        if lat is not None and lon is not None:
            clauses.append(
                """
                ST_DWithin(
                    geom::geography,
                    ST_SetSRID(
                        ST_MakePoint(
                            CAST(:lon AS DOUBLE PRECISION),
                            CAST(:lat AS DOUBLE PRECISION)
                        ),
                        4326
                    )::geography,
                    CAST(:radius_m AS DOUBLE PRECISION)
                )
                """
            )
            params.update({"lat": lat, "lon": lon, "radius_m": radius_m or 5000})

        sql = f"""
            SELECT
                id,
                canonical_brand,
                name,
                original_address,
                normalized_address,
                latitude,
                longitude,
                confidence_score,
                osm_type,
                osm_id,
                CASE
                    WHEN CAST(:lat AS DOUBLE PRECISION) IS NULL
                        OR CAST(:lon AS DOUBLE PRECISION) IS NULL THEN NULL
                    ELSE ST_Distance(
                        geom::geography,
                        ST_SetSRID(
                            ST_MakePoint(
                                CAST(:lon AS DOUBLE PRECISION),
                                CAST(:lat AS DOUBLE PRECISION)
                            ),
                            4326
                        )::geography
                    )
                END AS distance_m
            FROM known_pois
            WHERE {' AND '.join(clauses)}
            ORDER BY confidence_score DESC NULLS LAST, updated_at DESC
            LIMIT :limit
        """
        params.setdefault("lat", lat)
        params.setdefault("lon", lon)
        result = await self.db.execute(text(sql), params)
        return [dict(row) for row in result.mappings().all()]

    def _candidate_from_row(
        self,
        row: dict[str, Any],
        *,
        normalized_text: str,
        lat: float | None,
        lon: float | None,
    ) -> PoiCandidate:
        confidence = float(row["confidence_score"]) if row.get("confidence_score") is not None else 0.65
        address = row.get("original_address")
        normalized_address = row.get("normalized_address")
        score = _score_row(
            normalized_query=normalized_text,
            normalized_address=normalized_address,
            name=row.get("name"),
            brand=row.get("canonical_brand"),
            confidence=confidence,
            distance_m=float(row["distance_m"]) if row.get("distance_m") is not None else None,
        )
        return PoiCandidate(
            id=int(row["id"]),
            canonical_brand=row["canonical_brand"],
            name=row.get("name"),
            address=address,
            normalized_address=normalized_address,
            latitude=float(row["latitude"]),
            longitude=float(row["longitude"]),
            confidence_score=confidence,
            distance_m=float(row["distance_m"]) if row.get("distance_m") is not None else None,
            osm_type=row.get("osm_type"),
            osm_id=int(row["osm_id"]) if row.get("osm_id") is not None else None,
            score=score,
        )


def _normalize_query(value: str) -> str:
    if not value:
        return ""
    try:
        return normalize_address(value, default_city=None).normalized_address
    except ValueError:
        return normalize_brand_text(value)


def _score_row(
    *,
    normalized_query: str,
    normalized_address: str | None,
    name: str | None,
    brand: str | None,
    confidence: float,
    distance_m: float | None,
) -> float:
    address_text = normalize_brand_text(normalized_address)
    name_text = normalize_brand_text(name)
    brand_text = normalize_brand_text(brand)
    haystack = " ".join(part for part in [address_text, name_text, brand_text] if part)
    query = normalize_brand_text(normalized_query)
    text_score = SequenceMatcher(None, query, normalize_brand_text(haystack)).ratio() if query and haystack else 0.0
    query_has_locator = len(query.split()) >= 3 or any(char.isdigit() for char in query)
    if query and address_text and query == address_text:
        text_score = 1.0
    elif query and query_has_locator and query in normalize_brand_text(haystack):
        text_score = max(text_score, 0.96)
    elif query and query in normalize_brand_text(haystack):
        text_score = max(text_score, 0.88)
    distance_score = 0.0
    if distance_m is not None:
        distance_score = max(0.0, min(1.0, 1.0 - (distance_m / 5000.0)))
    score = (text_score * 0.62) + (confidence * 0.28) + (distance_score * 0.10)
    return round(max(0.0, min(score, 1.0)), 4)


def poi_candidate_to_api(candidate: PoiCandidate) -> dict[str, Any]:
    return {
        "id": candidate.id,
        "canonical_brand": candidate.canonical_brand,
        "name": candidate.name,
        "address": candidate.address,
        "latitude": candidate.latitude,
        "longitude": candidate.longitude,
        "confidence_score": candidate.confidence_score,
        "distance_m": candidate.distance_m,
        "osm_type": candidate.osm_type,
        "osm_id": candidate.osm_id,
        "source": "known_pois",
    }
