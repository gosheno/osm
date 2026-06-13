from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.geocoder_factory import get_geocoder
from app.clients.opencage_client import OpenCageClient, OpenCageConfigError
from app.core.config import settings
from app.schemas.geocoding import GeocodingContextInput
from app.schemas.parsed_address import ParsedAddress
from app.services.address_normalizer import normalize_address as parse_address
from app.services.geocoding_context import (
    GeocodingContext,
    build_context,
    build_viewbox,
    distance_to_context,
    is_within_work_area,
)
from app.services.poi_matcher import PoiCandidate as KnownPoiCandidate
from app.services.poi_matcher import PoiMatcher
from app.utils.address_normalizer import NormalizedAddress, normalize_address


STOP_WORDS = {
    "г",
    "город",
    "дом",
    "д",
    "корпус",
    "к",
    "строение",
    "литера",
    "санкт",
    "петербург",
    "санкт-петербург",
    "ленинградская",
    "область",
    "россия",
}


@dataclass(frozen=True)
class CandidateScore:
    candidate: Any
    score: float
    distance_to_context_m: float | None
    has_required_house_match: bool


@dataclass(frozen=True)
class SearchAttempt:
    query: str
    provider: str
    status: str
    candidates_count: int
    score: float | None = None
    distance_to_context_m: float | None = None
    selected: bool = False
    error: str | None = None


class OpenCageFallbackUnavailableError(Exception):
    pass


class AddressService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.geocoder = get_geocoder()

    async def geocode_address(
        self,
        address: str,
        default_city: str | None = "санкт-петербург",
        place_name: str | None = None,
        force_refresh: bool = False,
        geocoding_context: GeocodingContextInput | dict | None = None,
        geocoding_area: str | None = None,
    ) -> dict:
        context = build_context(geocoding_context, geocoding_area)
        normalized = normalize_address(
            address,
            default_city=self._normalization_default_city(
                default_city=default_city,
                context=context,
                geocoding_context=geocoding_context,
                geocoding_area=geocoding_area,
            ),
            place_name=place_name,
        )

        provider = settings.GEOCODER_PROVIDER.lower().strip()
        if not force_refresh:
            try:
                poi_resolution = await PoiMatcher(self.db).resolve_or_return_candidates(
                    normalized.original_address
                )
                if poi_resolution.matched is not None:
                    row = await self._upsert_known_poi_address(
                        normalized=normalized,
                        poi=poi_resolution.matched,
                    )
                    return self._response_from_known_poi(
                        row,
                        normalized=normalized,
                        poi=poi_resolution.matched,
                        context=context,
                    )
            except Exception:
                rollback = getattr(self.db, "rollback", None)
                if rollback is not None:
                    await rollback()
                pass

        existing = await self._get_by_normalized_address(normalized.normalized_address)

        if (
            existing
            and not force_refresh
            and existing["geocoding_status"] == "found"
        ):
            await self._touch_address(existing["id"])
            return self._response_from_row(
                existing,
                source="database",
                normalized=normalized,
            )

        parsed = parse_address(
            normalized.normalized_address,
            context=context,
            place_name=normalized.place_name,
        )

        (
            candidates,
            used_provider,
            used_query,
            geocoding_score,
            region_hint,
            distance_to_context_m,
            attempts,
            has_required_house_match,
        ) = await self._search_with_queries(parsed, provider, context)

        provider_error = self._first_provider_error(attempts)
        if provider_error and not candidates:
            return {
                "id": None,
                "original_address": normalized.original_address,
                "address_for_geocoding": normalized.address_for_geocoding,
                "normalized_address": normalized.normalized_address,
                "place_name": normalized.place_name,
                "latitude": None,
                "longitude": None,
                "geocoding_status": "error",
                "geocoding_provider": used_provider,
                "confidence_score": None,
                "geocoding_score": None,
                "source": used_provider,
                "geocoding_query": used_query,
                "display_name": None,
                "error": provider_error,
                **self._context_response(context),
            }

        if not candidates or geocoding_score is None or geocoding_score < 35:
            row = await self._upsert_not_found(
                original_address=normalized.address_for_geocoding,
                normalized_address=normalized.normalized_address,
                geocoding_provider=used_provider,
                geocoding_query_used=used_query,
                cleaned_address=parsed.cleaned_address,
                normalized_key=parsed.normalized_key,
                region_hint=region_hint,
                settlement_hint=parsed.settlement_hint,
                context=context,
            )
            await self._save_attempts(
                row["id"],
                normalized=normalized,
                attempts=attempts,
                context=context,
            )

            return {
                "id": row["id"],
                "original_address": normalized.original_address,
                "address_for_geocoding": normalized.address_for_geocoding,
                "normalized_address": row["normalized_address"],
                "place_name": normalized.place_name,
                "latitude": None,
                "longitude": None,
                "geocoding_status": "not_found",
                "geocoding_provider": row["geocoding_provider"],
                "confidence_score": None,
                "geocoding_score": None,
                "source": used_provider,
                "geocoding_query": used_query,
                "display_name": None,
                "error": "Address was not found",
                **self._context_response(context),
            }

        best = candidates[0]
        confidence_score = self._calculate_confidence(
            best,
            used_provider,
            used_query or normalized.normalized_address,
        )
        status = (
            "found"
            if geocoding_score >= 80 and has_required_house_match
            else "ambiguous"
        )

        row = await self._upsert_found(
            original_address=normalized.address_for_geocoding,
            normalized_address=normalized.normalized_address,
            latitude=best.latitude,
            longitude=best.longitude,
            confidence_score=confidence_score,
            geocoding_status=status,
            geocoding_provider=used_provider,
            geocoding_query_used=used_query,
            geocoding_score=geocoding_score,
            cleaned_address=parsed.cleaned_address,
            normalized_key=parsed.normalized_key,
            region_hint=region_hint,
            settlement_hint=parsed.settlement_hint,
            context=context,
        )
        await self._save_attempts(
            row["id"],
            normalized=normalized,
            attempts=attempts,
            context=context,
        )

        return {
            "id": row["id"],
            "original_address": normalized.original_address,
            "address_for_geocoding": normalized.address_for_geocoding,
            "normalized_address": row["normalized_address"],
            "place_name": normalized.place_name,
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "geocoding_status": row["geocoding_status"],
            "geocoding_provider": row["geocoding_provider"],
            "confidence_score": (
                float(row["confidence_score"])
                if row["confidence_score"] is not None
                else None
            ),
            "geocoding_score": geocoding_score,
            "source": used_provider,
            "geocoding_query": used_query,
            "display_name": best.display_name,
            "error": None,
            "distance_to_context_m": distance_to_context_m,
            **self._context_response(context),
        }

    def _normalization_default_city(
        self,
        *,
        default_city: str | None,
        context: GeocodingContext,
        geocoding_context: GeocodingContextInput | dict | None,
        geocoding_area: str | None,
    ) -> str | None:
        if geocoding_context is not None:
            return None
        if geocoding_area:
            return None
        if context.type in {"district", "custom_area"} and context.label:
            return None
        return default_city

    async def _search_with_queries(
        self,
        parsed: ParsedAddress,
        provider: str,
        context: GeocodingContext,
    ) -> tuple[list, str, str | None, float | None, str | None, float | None, list[SearchAttempt], bool]:
        best: CandidateScore | None = None
        best_provider = provider
        best_query: str | None = None
        best_region = parsed.region_hint
        attempts: list[SearchAttempt] = []

        for query in parsed.geocoding_queries:
            try:
                candidates, used_provider = await self._search_with_optional_fallback(
                    query.query,
                    provider,
                    context=context,
                )
                if best is None:
                    best_provider = used_provider
            except Exception as exc:
                error_provider = (
                    "opencage"
                    if isinstance(exc, OpenCageFallbackUnavailableError)
                    else provider
                )
                if best is None:
                    best_provider = error_provider
                attempts.append(
                    SearchAttempt(
                        query=query.query,
                        provider=error_provider,
                        status="error",
                        candidates_count=0,
                        error=str(exc),
                    )
                )
                continue

            scored = self._score_candidates(
                candidates,
                query=query.query,
                provider=used_provider,
                region_hint=query.region_hint or parsed.region_hint,
                parsed=parsed,
                context=context,
            )
            attempts.append(
                SearchAttempt(
                    query=query.query,
                    provider=used_provider,
                    status="found" if scored else "not_found",
                    candidates_count=len(candidates),
                    score=scored.score if scored else None,
                    distance_to_context_m=(
                        scored.distance_to_context_m if scored else None
                    ),
                )
            )

            if scored is None:
                continue

            if best is None or scored.score > best.score:
                best = scored
                best_provider = used_provider
                best_query = query.query
                best_region = query.region_hint or parsed.region_hint

            if scored.score >= 90 and scored.has_required_house_match:
                break

        if best_query is not None:
            attempts = [
                SearchAttempt(
                    query=attempt.query,
                    provider=attempt.provider,
                    status=attempt.status,
                    candidates_count=attempt.candidates_count,
                    score=attempt.score,
                    distance_to_context_m=attempt.distance_to_context_m,
                    selected=attempt.query == best_query,
                    error=attempt.error,
                )
                for attempt in attempts
            ]

        if best is None:
            return [], best_provider, best_query, None, best_region, None, attempts, False

        return (
            [best.candidate],
            best_provider,
            best_query,
            round(best.score, 2),
            best_region,
            best.distance_to_context_m,
            attempts,
            best.has_required_house_match,
        )

    async def _search_with_optional_fallback(
        self,
        query: str,
        provider: str,
        *,
        context: GeocodingContext,
    ) -> tuple[list, str]:
        try:
            candidates = await self._call_search(self.geocoder, query, provider, context)
        except Exception as exc:
            if provider == "nominatim" and settings.GEOCODER_ENABLE_FALLBACK:
                fallback_candidates = await self._search_opencage_fallback(
                    query,
                    reason=str(exc),
                )
                return fallback_candidates, "opencage"
            raise

        if candidates:
            return candidates, provider

        if provider == "nominatim" and settings.GEOCODER_ENABLE_FALLBACK:
            fallback_candidates = await self._search_opencage_fallback(
                query,
                reason="Nominatim returned no candidates",
            )
            return fallback_candidates, "opencage"

        return [], provider

    async def _call_search(
        self,
        geocoder,
        query: str,
        provider: str,
        context: GeocodingContext,
    ) -> list:
        if provider == "nominatim":
            try:
                return await geocoder.search(query, limit=5, context=context)
            except TypeError:
                try:
                    return await geocoder.search(query, limit=5)
                except TypeError:
                    return await geocoder.search(query)

        try:
            return await geocoder.search(query, limit=5)
        except TypeError:
            return await geocoder.search(query)

    async def _search_opencage_fallback(self, query: str, *, reason: str) -> list:
        try:
            return await OpenCageClient().search(query, limit=5)
        except OpenCageConfigError as exc:
            raise OpenCageFallbackUnavailableError(
                "OpenCage fallback is required because "
                f"{reason}, but OPENCAGE_API_KEY is not set."
            ) from exc
        except Exception as exc:
            raise OpenCageFallbackUnavailableError(
                "OpenCage fallback failed after Nominatim could not resolve "
                f"the query: {exc}"
            ) from exc

    def _score_candidates(
        self,
        candidates: list,
        *,
        query: str,
        provider: str,
        region_hint: str | None,
        parsed: ParsedAddress,
        context: GeocodingContext,
    ) -> CandidateScore | None:
        if not candidates:
            return None

        scored = [
            self._score_candidate(
                candidate,
                query=query,
                provider=provider,
                region_hint=region_hint,
                parsed=parsed,
                context=context,
            )
            for candidate in candidates
        ]
        return max(scored, key=lambda item: item.score)

    def _score_candidate(
        self,
        candidate,
        *,
        query: str,
        provider: str,
        region_hint: str | None,
        parsed: ParsedAddress,
        context: GeocodingContext,
    ) -> CandidateScore:
        score = 30.0
        display_name = (candidate.display_name or "").lower().replace("ё", "е")
        query_tokens = self._significant_tokens(query)

        for token in query_tokens:
            if token in display_name:
                score += 4.0

        score += self._provider_score(candidate, provider)

        place_rank = getattr(candidate, "place_rank", None)
        if place_rank is not None:
            if place_rank >= 30:
                score += 10.0
            elif place_rank <= 26 and parsed.house:
                score -= 20.0

        if parsed.street:
            street_tokens = self._significant_tokens(parsed.street)
            if street_tokens and all(token in display_name for token in street_tokens[:2]):
                score += 12.0

        has_house_match = self._has_required_house_match(candidate, parsed)
        if parsed.house:
            score += 25.0 if has_house_match else -35.0

        if region_hint:
            region_lower = region_hint.lower().replace("ё", "е")
            if "санкт" in region_lower and (
                "санкт-петербург" in display_name or "петербург" in display_name
            ):
                score += 10.0
            elif "ленинград" in region_lower and "ленинградская область" in display_name:
                score += 10.0
            elif "россия" in display_name:
                score -= 5.0

        distance_m: float | None = None
        if candidate.latitude is not None and candidate.longitude is not None:
            if is_within_work_area(candidate.latitude, candidate.longitude):
                distance_m = distance_to_context(
                    candidate.latitude,
                    candidate.longitude,
                    context,
                )
                if distance_m <= context.radius_km * 1000:
                    score += 20.0
                else:
                    score -= 20.0
                if distance_m <= 3000:
                    score += 10.0
            else:
                score -= 50.0

        return CandidateScore(
            candidate=candidate,
            score=max(0.0, min(score, 100.0)),
            distance_to_context_m=distance_m,
            has_required_house_match=has_house_match,
        )

    def _significant_tokens(self, value: str) -> list[str]:
        tokens = re.findall(r"[0-9a-zа-я-]+", value.lower().replace("ё", "е"))
        return [
            token
            for token in tokens
            if len(token) > 1 and token not in STOP_WORDS
        ]

    def _has_required_house_match(self, candidate, parsed: ParsedAddress) -> bool:
        if not parsed.house:
            return True

        house = parsed.house.lower().replace("ё", "е")
        display_name = (candidate.display_name or "").lower().replace("ё", "е")
        raw_address = self._candidate_raw_address(candidate)
        raw_house = (
            raw_address.get("house_number")
            or raw_address.get("house")
            or raw_address.get("building")
        )

        if raw_house and str(raw_house).lower().replace("ё", "е") == house:
            return True

        return bool(re.search(rf"(^|[\s,/]){re.escape(house)}($|[\s,/])", display_name))

    def _candidate_raw_address(self, candidate) -> dict:
        raw = getattr(candidate, "raw", None)
        if not isinstance(raw, dict):
            return {}
        address = raw.get("address")
        return address if isinstance(address, dict) else {}

    def _provider_score(self, candidate, provider: str) -> float:
        if provider == "opencage":
            confidence = getattr(candidate, "confidence", None)
            return min(float(confidence or 0) * 6.0, 45.0)

        importance = getattr(candidate, "importance", None)
        return min(float(importance or 0) * 40.0, 35.0)

    def _calculate_confidence(self, best, provider: str, query: str) -> float | None:
        if provider == "opencage":
            return float(best.confidence) if best.confidence is not None else None
        else:
            importance = getattr(best, "importance", None)
            return round(float(importance) * 100, 2) if importance is not None else None

    def _first_provider_error(self, attempts: list[SearchAttempt]) -> str | None:
        for attempt in attempts:
            if attempt.status == "error" and attempt.error:
                return attempt.error
        return None

    def _response_from_row(
        self,
        row: dict,
        source: str,
        normalized: NormalizedAddress | None = None,
    ) -> dict:
        status = row["geocoding_status"]

        return {
            "id": row["id"],
            "original_address": (
                normalized.original_address
                if normalized is not None
                else row["original_address"]
            ),
            "address_for_geocoding": (
                normalized.address_for_geocoding
                if normalized is not None
                else row["original_address"]
            ),
            "normalized_address": row["normalized_address"],
            "place_name": normalized.place_name if normalized is not None else None,
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "geocoding_status": status,
            "geocoding_provider": row["geocoding_provider"],
            "confidence_score": (
                float(row["confidence_score"])
                if row["confidence_score"] is not None
                else None
            ),
            "geocoding_score": self._row_get_float(row, "geocoding_score"),
            "source": source,
            "geocoding_query": self._row_get(row, "geocoding_query_used"),
            "display_name": None,
            "error": "Address was not found" if status == "not_found" else None,
            "geocoding_context_label": self._row_get(row, "geocoding_context_label"),
            "distance_to_context_m": None,
        }

    def _response_from_known_poi(
        self,
        row: dict,
        *,
        normalized: NormalizedAddress,
        poi: KnownPoiCandidate,
        context: GeocodingContext,
    ) -> dict:
        return {
            "id": row["id"],
            "original_address": normalized.original_address,
            "address_for_geocoding": normalized.address_for_geocoding,
            "normalized_address": row["normalized_address"],
            "place_name": normalized.place_name,
            "latitude": row["latitude"],
            "longitude": row["longitude"],
            "geocoding_status": row["geocoding_status"],
            "geocoding_provider": row["geocoding_provider"],
            "confidence_score": (
                float(row["confidence_score"])
                if row["confidence_score"] is not None
                else None
            ),
            "geocoding_score": self._row_get_float(row, "geocoding_score"),
            "source": "known_poi",
            "geocoding_query": self._row_get(row, "geocoding_query_used"),
            "display_name": row["display_name"] or poi.address or poi.name,
            "error": None,
            "distance_to_context_m": poi.distance_m,
            **self._context_response(context),
        }

    async def _get_by_normalized_address(self, normalized_address: str) -> dict | None:
        result = await self.db.execute(
            text(
                """
                SELECT
                    id,
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geocoding_status,
                    geocoding_provider,
                    confidence_score,
                    geocoding_query_used,
                    geocoding_score,
                    geocoding_context_label,
                    geocoding_context_latitude,
                    geocoding_context_longitude,
                    geocoding_context_radius_km,
                    geocoding_context_source
                FROM addresses
                WHERE normalized_address = :normalized_address
                """
            ),
            {"normalized_address": normalized_address},
        )

        return result.mappings().first()

    async def _touch_address(self, address_id: int) -> None:
        await self.db.execute(
            text(
                """
                UPDATE addresses
                SET last_used_at = now()
                WHERE id = :address_id
                """
            ),
            {"address_id": address_id},
        )
        await self.db.commit()

    async def _upsert_found(
        self,
        *,
        original_address: str,
        normalized_address: str,
        latitude: float,
        longitude: float,
        confidence_score: float | None,
        geocoding_status: str,
        geocoding_provider: str,
        geocoding_query_used: str | None,
        geocoding_score: float | None,
        cleaned_address: str | None,
        normalized_key: str | None,
        region_hint: str | None,
        settlement_hint: str | None,
        context: GeocodingContext,
    ) -> dict:
        result = await self.db.execute(
            text(
                """
                INSERT INTO addresses (
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geom,
                    geocoding_status,
                    geocoding_provider,
                    confidence_score,
                    geocoding_query_used,
                    geocoding_score,
                    cleaned_address,
                    normalized_key,
                    region_hint,
                    settlement_hint,
                    geocoding_context_label,
                    geocoding_context_latitude,
                    geocoding_context_longitude,
                    geocoding_context_radius_km,
                    geocoding_context_source,
                    last_used_at
                )
                VALUES (
                    :original_address,
                    :normalized_address,
                    :latitude,
                    :longitude,
                    ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326),
                    :geocoding_status,
                    :geocoding_provider,
                    :confidence_score,
                    :geocoding_query_used,
                    :geocoding_score,
                    :cleaned_address,
                    :normalized_key,
                    :region_hint,
                    :settlement_hint,
                    :geocoding_context_label,
                    :geocoding_context_latitude,
                    :geocoding_context_longitude,
                    :geocoding_context_radius_km,
                    :geocoding_context_source,
                    now()
                )
                ON CONFLICT (normalized_address)
                DO UPDATE SET
                    original_address = EXCLUDED.original_address,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    geom = EXCLUDED.geom,
                    geocoding_status = EXCLUDED.geocoding_status,
                    geocoding_provider = EXCLUDED.geocoding_provider,
                    confidence_score = EXCLUDED.confidence_score,
                    geocoding_query_used = EXCLUDED.geocoding_query_used,
                    geocoding_score = EXCLUDED.geocoding_score,
                    cleaned_address = EXCLUDED.cleaned_address,
                    normalized_key = EXCLUDED.normalized_key,
                    region_hint = EXCLUDED.region_hint,
                    settlement_hint = EXCLUDED.settlement_hint,
                    geocoding_context_label = EXCLUDED.geocoding_context_label,
                    geocoding_context_latitude = EXCLUDED.geocoding_context_latitude,
                    geocoding_context_longitude = EXCLUDED.geocoding_context_longitude,
                    geocoding_context_radius_km = EXCLUDED.geocoding_context_radius_km,
                    geocoding_context_source = EXCLUDED.geocoding_context_source,
                    last_used_at = now()
                RETURNING
                    id,
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geocoding_status,
                    geocoding_provider,
                    confidence_score
                """
            ),
            {
                "original_address": original_address,
                "normalized_address": normalized_address,
                "latitude": latitude,
                "longitude": longitude,
                "confidence_score": confidence_score,
                "geocoding_status": geocoding_status,
                "geocoding_provider": geocoding_provider,
                "geocoding_query_used": geocoding_query_used,
                "geocoding_score": geocoding_score,
                "cleaned_address": cleaned_address,
                "normalized_key": normalized_key,
                "region_hint": region_hint,
                "settlement_hint": settlement_hint,
                **self._context_params(context),
            },
        )

        await self.db.commit()
        return result.mappings().one()

    async def _upsert_known_poi_address(
        self,
        *,
        normalized: NormalizedAddress,
        poi: KnownPoiCandidate,
    ) -> dict:
        raw_json = json.dumps(
            {
                "source": "known_pois",
                "known_poi_id": poi.id,
                "canonical_brand": poi.canonical_brand,
                "name": poi.name,
                "address": poi.address,
                "distance_m": poi.distance_m,
                "match_score": poi.score,
            },
            ensure_ascii=False,
        )
        result = await self.db.execute(
            text(
                """
                INSERT INTO addresses (
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geom,
                    geocoding_status,
                    geocoding_provider,
                    confidence_score,
                    geocoding_query_used,
                    geocoding_score,
                    display_name,
                    osm_type,
                    osm_id,
                    raw_response,
                    last_used_at
                )
                VALUES (
                    :original_address,
                    :normalized_address,
                    :latitude,
                    :longitude,
                    ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326),
                    'found',
                    'known_poi',
                    :confidence_score,
                    :geocoding_query_used,
                    :geocoding_score,
                    :display_name,
                    :osm_type,
                    :osm_id,
                    CAST(:raw_response AS jsonb),
                    now()
                )
                ON CONFLICT (normalized_address)
                DO UPDATE SET
                    original_address = EXCLUDED.original_address,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    geom = EXCLUDED.geom,
                    geocoding_status = 'found',
                    geocoding_provider = 'known_poi',
                    confidence_score = EXCLUDED.confidence_score,
                    geocoding_query_used = EXCLUDED.geocoding_query_used,
                    geocoding_score = EXCLUDED.geocoding_score,
                    display_name = EXCLUDED.display_name,
                    osm_type = EXCLUDED.osm_type,
                    osm_id = EXCLUDED.osm_id,
                    raw_response = EXCLUDED.raw_response,
                    last_used_at = now()
                RETURNING
                    id,
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geocoding_status,
                    geocoding_provider,
                    confidence_score,
                    geocoding_query_used,
                    geocoding_score,
                    display_name
                """
            ),
            {
                "original_address": normalized.address_for_geocoding,
                "normalized_address": normalized.normalized_address,
                "latitude": poi.latitude,
                "longitude": poi.longitude,
                "confidence_score": round((poi.confidence_score or 0.0) * 100, 2),
                "geocoding_query_used": normalized.normalized_address,
                "geocoding_score": round(poi.score * 100, 2),
                "display_name": poi.address or poi.name or poi.canonical_brand,
                "osm_type": poi.osm_type,
                "osm_id": poi.osm_id,
                "raw_response": raw_json,
            },
        )
        await self.db.commit()
        return result.mappings().one()

    async def _upsert_not_found(
        self,
        *,
        original_address: str,
        normalized_address: str,
        geocoding_provider: str,
        geocoding_query_used: str | None,
        cleaned_address: str | None,
        normalized_key: str | None,
        region_hint: str | None,
        settlement_hint: str | None,
        context: GeocodingContext,
    ) -> dict:
        result = await self.db.execute(
            text(
                """
                INSERT INTO addresses (
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geom,
                    geocoding_status,
                    geocoding_provider,
                    geocoding_query_used,
                    cleaned_address,
                    normalized_key,
                    region_hint,
                    settlement_hint,
                    geocoding_context_label,
                    geocoding_context_latitude,
                    geocoding_context_longitude,
                    geocoding_context_radius_km,
                    geocoding_context_source,
                    last_used_at
                )
                VALUES (
                    :original_address,
                    :normalized_address,
                    NULL,
                    NULL,
                    NULL,
                    'not_found',
                    :geocoding_provider,
                    :geocoding_query_used,
                    :cleaned_address,
                    :normalized_key,
                    :region_hint,
                    :settlement_hint,
                    :geocoding_context_label,
                    :geocoding_context_latitude,
                    :geocoding_context_longitude,
                    :geocoding_context_radius_km,
                    :geocoding_context_source,
                    now()
                )
                ON CONFLICT (normalized_address)
                DO UPDATE SET
                    original_address = EXCLUDED.original_address,
                    latitude = NULL,
                    longitude = NULL,
                    geom = NULL,
                    geocoding_status = 'not_found',
                    geocoding_provider = :geocoding_provider,
                    geocoding_query_used = EXCLUDED.geocoding_query_used,
                    geocoding_score = NULL,
                    cleaned_address = EXCLUDED.cleaned_address,
                    normalized_key = EXCLUDED.normalized_key,
                    region_hint = EXCLUDED.region_hint,
                    settlement_hint = EXCLUDED.settlement_hint,
                    geocoding_context_label = EXCLUDED.geocoding_context_label,
                    geocoding_context_latitude = EXCLUDED.geocoding_context_latitude,
                    geocoding_context_longitude = EXCLUDED.geocoding_context_longitude,
                    geocoding_context_radius_km = EXCLUDED.geocoding_context_radius_km,
                    geocoding_context_source = EXCLUDED.geocoding_context_source,
                    last_used_at = now()
                RETURNING
                    id,
                    original_address,
                    normalized_address,
                    latitude,
                    longitude,
                    geocoding_status,
                    geocoding_provider,
                    confidence_score
                """
            ),
            {
                "original_address": original_address,
                "normalized_address": normalized_address,
                "geocoding_provider": geocoding_provider,
                "geocoding_query_used": geocoding_query_used,
                "cleaned_address": cleaned_address,
                "normalized_key": normalized_key,
                "region_hint": region_hint,
                "settlement_hint": settlement_hint,
                **self._context_params(context),
            },
        )

        await self.db.commit()
        return result.mappings().one()

    async def _save_attempts(
        self,
        address_id: int,
        *,
        normalized: NormalizedAddress,
        attempts: list[SearchAttempt],
        context: GeocodingContext,
    ) -> None:
        if not attempts:
            return

        try:
            for attempt in attempts:
                await self.db.execute(
                    text(
                        """
                        INSERT INTO geocoding_attempts (
                            address_id,
                            original_address,
                            normalized_address,
                            query,
                            provider,
                            status,
                            candidates_count,
                            score,
                            selected,
                            viewbox,
                            bounded,
                            distance_to_context_m,
                            error
                        )
                        VALUES (
                            :address_id,
                            :original_address,
                            :normalized_address,
                            :query,
                            :provider,
                            :status,
                            :candidates_count,
                            :score,
                            :selected,
                            :viewbox,
                            :bounded,
                            :distance_to_context_m,
                            :error
                        )
                        """
                    ),
                    {
                        "address_id": address_id,
                        "original_address": normalized.original_address,
                        "normalized_address": normalized.normalized_address,
                        "query": attempt.query,
                        "provider": attempt.provider,
                        "status": attempt.status,
                        "candidates_count": attempt.candidates_count,
                        "score": attempt.score,
                        "selected": attempt.selected,
                        "viewbox": build_viewbox(context),
                        "bounded": context.bounded,
                        "distance_to_context_m": attempt.distance_to_context_m,
                        "error": attempt.error,
                    },
                )
            await self.db.commit()
        except Exception:
            rollback = getattr(self.db, "rollback", None)
            if rollback is not None:
                await rollback()

    def _context_params(self, context: GeocodingContext) -> dict:
        return {
            "geocoding_context_label": context.label,
            "geocoding_context_latitude": context.latitude,
            "geocoding_context_longitude": context.longitude,
            "geocoding_context_radius_km": context.radius_km,
            "geocoding_context_source": context.source,
        }

    def _context_response(self, context: GeocodingContext) -> dict:
        return {
            "geocoding_context_label": context.label,
            "geocoding_context_latitude": context.latitude,
            "geocoding_context_longitude": context.longitude,
            "geocoding_context_radius_km": context.radius_km,
            "geocoding_context_source": context.source,
        }

    def _row_get(self, row: dict, key: str):
        if hasattr(row, "get"):
            return row.get(key)
        try:
            return row[key]
        except KeyError:
            return None

    def _row_get_float(self, row: dict, key: str) -> float | None:
        value = self._row_get(row, key)
        return float(value) if value is not None else None
