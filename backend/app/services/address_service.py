import re
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.geocoder_factory import get_geocoder
from app.clients.opencage_client import OpenCageClient, OpenCageConfigError
from app.core.config import settings
from app.utils.address_normalizer import NormalizedAddress, normalize_address
from app.services.address_normalizer import normalize_address as parse_address
from app.schemas.parsed_address import ParsedAddress


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
    ) -> dict:
        normalized = normalize_address(
            address,
            default_city=default_city,
            place_name=place_name,
        )

        provider = settings.GEOCODER_PROVIDER.lower().strip()

        existing = await self._get_by_normalized_address(normalized.normalized_address)

        if (
            existing
            and not force_refresh
            and existing["geocoding_status"]
            in ("found", "not_found")
        ):
            await self._touch_address(existing["id"])

            return self._response_from_row(
                existing,
                source="database",
                normalized=normalized,
            )

        parsed: ParsedAddress = parse_address(normalized.normalized_address)

        candidates, used_provider, used_query, geocoding_score, region_hint = await self._search_with_queries(
            parsed, provider
        )

        if not candidates:
            row = await self._upsert_not_found(
                original_address=normalized.address_for_geocoding,
                normalized_address=normalized.normalized_address,
                geocoding_provider=used_provider,
                geocoding_query_used=used_query,
                cleaned_address=parsed.cleaned,
                normalized_key=parsed.normalized_key,
                region_hint=region_hint,
                settlement_hint=parsed.settlement_hint,
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
                "source": used_provider,
                "geocoding_query": used_query,
                "display_name": None,
                "error": "Address was not found",
            }

        best = candidates[0]

        latitude = best.latitude
        longitude = best.longitude
        display_name = best.display_name

        confidence_score = self._calculate_confidence(best, used_provider, used_query or normalized.normalized_address)
        status = "found"
        if geocoding_score is not None and geocoding_score < 80:
            status = "ambiguous"

        row = await self._upsert_found(
            original_address=normalized.address_for_geocoding,
            normalized_address=normalized.normalized_address,
            latitude=latitude,
            longitude=longitude,
            confidence_score=confidence_score,
            geocoding_status=status,
            geocoding_provider=used_provider,
            geocoding_query_used=used_query,
            geocoding_score=geocoding_score,
            cleaned_address=parsed.cleaned,
            normalized_key=parsed.normalized_key,
            region_hint=region_hint,
            settlement_hint=parsed.settlement_hint,
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
            "confidence_score": float(row["confidence_score"]) if row["confidence_score"] is not None else None,
            "source": used_provider,
            "geocoding_query": used_query,
            "display_name": display_name,
            "error": None,
        }

    async def _search_with_queries(
        self,
        parsed: ParsedAddress,
        provider: str,
    ) -> tuple[list, str, str | None, float | None, str | None]:
        """Try parsed.geocoding_queries in priority order and return first non-empty result.

        Returns (candidates, used_provider, used_query, score, region_hint)
        """
        best: tuple[list, str, str | None, float | None, str | None] = (
            [],
            provider,
            None,
            None,
            parsed.region_hint,
        )

        queries = sorted(parsed.geocoding_queries, key=lambda q: q.priority, reverse=True)

        for q in queries:
            try:
                candidates, used_provider = await self._search_with_optional_fallback(q.query, provider)
            except Exception:
                continue

            if not candidates:
                continue

            scored = self._score_candidates(candidates, q.query, used_provider, q.region_hint or parsed.region_hint)
            if scored is None:
                continue

            best_candidate, best_score = scored
            if best_score is None:
                continue

            if best[3] is None or best_score > best[3]:
                best = ([best_candidate], used_provider, q.query, best_score, q.region_hint or parsed.region_hint)

            if best_score >= 80:
                return best

        return best

    async def _search_with_optional_fallback(
        self,
        query: str,
        provider: str,
    ) -> tuple[list, str]:
        try:
            candidates = await self.geocoder.search(query)
        except Exception:
            if provider == "nominatim":
                fallback_candidates = await self._search_opencage_fallback(query)
                if fallback_candidates:
                    return fallback_candidates, "opencage"
            raise

        if candidates:
            return candidates, provider

        if provider == "nominatim":
            fallback_candidates = await self._search_opencage_fallback(query)
            if fallback_candidates:
                return fallback_candidates, "opencage"

        return [], provider

    async def _search_opencage_fallback(self, query: str) -> list:
        try:
            return await OpenCageClient().search(query)
        except OpenCageConfigError:
            return []
        except Exception:
            return []

    def _calculate_confidence(self, best, provider: str, query: str) -> float | None:
        if provider == "opencage":
            confidence = float(best.confidence) if best.confidence is not None else None
        else:
            importance = getattr(best, "importance", None)
            confidence = round(float(importance) * 100, 2) if importance is not None else None

        if confidence is None:
            return None

        score = float(confidence)
        display_lower = best.display_name.lower()
        query_lower = query.lower()

        for token in query_lower.replace(",", " ").split():
            if token and token in display_lower:
                score += 2.0

        return min(score, 100.0)

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
            "source": source,
            "display_name": None,
            "error": "Address was not found" if status == "not_found" else None,
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
                    confidence_score
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
        original_address: str,
        normalized_address: str,
        latitude: float,
        longitude: float,
        confidence_score: float | None,
        geocoding_status: str = "found",
        geocoding_provider: str = "nominatim",
        geocoding_query_used: str | None = None,
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
            },
        )

        await self.db.commit()
        return result.mappings().one()

    async def _upsert_not_found(
        self,
        original_address: str,
        normalized_address: str,
        geocoding_provider: str = "nominatim",
        geocoding_query_used: str | None = None,
    ) -> dict:
        result = await self.db.execute(
            text(
                """
                INSERT INTO addresses (
                    original_address,
                    normalized_address,
                    geocoding_status,
                    geocoding_provider,
                    geocoding_query_used,
                    last_used_at
                )
                VALUES (
                    :original_address,
                    :normalized_address,
                    'not_found',
                    :geocoding_provider,
                    :geocoding_query_used,
                    now()
                )
                ON CONFLICT (normalized_address)
                DO UPDATE SET
                    original_address = EXCLUDED.original_address,
                    geocoding_status = 'not_found',
                    geocoding_provider = :geocoding_provider,
                    geocoding_query_used = EXCLUDED.geocoding_query_used,
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
            },
        )

        await self.db.commit()
        return result.mappings().one()
