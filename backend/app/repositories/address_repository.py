from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def get_address_by_normalized(
    db: AsyncSession,
    normalized_address: str,
) -> dict | None:
    result = await db.execute(
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

    row = result.mappings().first()
    return dict(row) if row else None


async def upsert_address(
    db: AsyncSession,
    *,
    original_address: str,
    normalized_address: str,
    latitude: float | None,
    longitude: float | None,
    geocoding_status: str,
    geocoding_provider: str | None,
    confidence_score: float | None,
) -> dict:
    if geocoding_status == "not_found":
        raise ValueError("not_found addresses must not be saved to addresses cache")

    result = await db.execute(
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
                CASE
                    WHEN :latitude IS NOT NULL AND :longitude IS NOT NULL
                    THEN ST_SetSRID(ST_MakePoint(:longitude, :latitude), 4326)
                    ELSE NULL
                END,
                :geocoding_status,
                :geocoding_provider,
                :confidence_score,
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
            "geocoding_status": geocoding_status,
            "geocoding_provider": geocoding_provider,
            "confidence_score": confidence_score,
        },
    )

    await db.commit()

    row = result.mappings().one()
    return dict(row)


async def touch_address_last_used(
    db: AsyncSession,
    address_id: int,
) -> None:
    await db.execute(
        text(
            """
            UPDATE addresses
            SET last_used_at = now()
            WHERE id = :address_id
            """
        ),
        {"address_id": address_id},
    )
    await db.commit()
