from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def save_route_batches(
    db: AsyncSession,
    *,
    total_distance_m: float | None,
    total_duration_s: float | None,
    batches,
    yandex_batches_by_number: dict[int, object],
) -> int:
    try:
        result = await db.execute(
            text(
                """
                INSERT INTO route_jobs (
                    status,
                    total_distance_m,
                    total_duration_s,
                    finished_at
                )
                VALUES (
                    'completed',
                    :total_distance_m,
                    :total_duration_s,
                    now()
                )
                RETURNING id
                """
            ),
            {
                "total_distance_m": total_distance_m,
                "total_duration_s": total_duration_s,
            },
        )
        route_job_id = int(result.scalar_one())

        for batch in batches:
            yandex_batch = yandex_batches_by_number.get(batch.batch_number)
            await db.execute(
                text(
                    """
                    INSERT INTO route_batches (
                        route_job_id,
                        batch_number,
                        points_count,
                        distance_m,
                        duration_s,
                        yandex_maps_url
                    )
                    VALUES (
                        :route_job_id,
                        :batch_number,
                        :points_count,
                        :distance_m,
                        :duration_s,
                        :yandex_maps_url
                    )
                    ON CONFLICT (route_job_id, batch_number)
                    DO UPDATE SET
                        points_count = EXCLUDED.points_count,
                        distance_m = EXCLUDED.distance_m,
                        duration_s = EXCLUDED.duration_s,
                        yandex_maps_url = EXCLUDED.yandex_maps_url
                    """
                ),
                {
                    "route_job_id": route_job_id,
                    "batch_number": batch.batch_number,
                    "points_count": batch.points_count,
                    "distance_m": batch.distance_m,
                    "duration_s": batch.duration_s,
                    "yandex_maps_url": (
                        yandex_batch.yandex_maps_url
                        if yandex_batch is not None
                        else None
                    ),
                },
            )

        await db.commit()
        return route_job_id
    except Exception:
        await db.rollback()
        raise
