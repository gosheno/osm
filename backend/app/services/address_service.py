from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.nominatim_client import NominatimClient
from app.utils.address_normalizer import NormalizedAddress, normalize_address


class AddressService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.geocoder = NominatimClient()

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

        existing = await self._get_by_normalized_address(normalized.normalized_address)

        if (
            existing
            and not force_refresh
            and existing["geocoding_status"]
            in ("found", "manual", "ambiguous", "not_found")
        ):
            await self._touch_address(existing["id"])

            return self._response_from_row(
                existing,
                source="database",
                normalized=normalized,
            )

        candidates = await self.geocoder.search(normalized.normalized_address)

        if not candidates:
            row = await self._upsert_not_found(
                original_address=normalized.address_for_geocoding,
                normalized_address=normalized.normalized_address,
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
                "geocoding_provider": "nominatim",
                "confidence_score": None,
                "source": "nominatim",
                "display_name": None,
                "error": "Address was not found",
            }

        best = candidates[0]

        latitude = best.latitude
        longitude = best.longitude
        importance = best.importance
        confidence_score = round(float(importance) * 100, 2) if importance is not None else None
        display_name = best.display_name

        row = await self._upsert_found(
            original_address=normalized.address_for_geocoding,
            normalized_address=normalized.normalized_address,
            latitude=latitude,
            longitude=longitude,
            confidence_score=confidence_score,
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
            "source": "nominatim",
            "display_name": display_name,
            "error": None,
        }

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
                    last_used_at
                )
                VALUES (
                    :original_address,
                    :normalized_address,
                    :latitude,
                    :longitude,
                    ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326),
                    'found',
                    'nominatim',
                    :confidence_score,
                    now()
                )
                ON CONFLICT (normalized_address)
                DO UPDATE SET
                    original_address = EXCLUDED.original_address,
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    geom = EXCLUDED.geom,
                    geocoding_status = 'found',
                    geocoding_provider = 'nominatim',
                    confidence_score = EXCLUDED.confidence_score,
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
            },
        )

        await self.db.commit()
        return result.mappings().one()

    async def _upsert_not_found(
        self,
        original_address: str,
        normalized_address: str,
    ) -> dict:
        result = await self.db.execute(
            text(
                """
                INSERT INTO addresses (
                    original_address,
                    normalized_address,
                    geocoding_status,
                    geocoding_provider,
                    last_used_at
                )
                VALUES (
                    :original_address,
                    :normalized_address,
                    'not_found',
                    'nominatim',
                    now()
                )
                ON CONFLICT (normalized_address)
                DO UPDATE SET
                    original_address = EXCLUDED.original_address,
                    geocoding_status = 'not_found',
                    geocoding_provider = 'nominatim',
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
            },
        )

        await self.db.commit()
        return result.mappings().one()
