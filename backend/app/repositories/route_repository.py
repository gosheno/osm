from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def save_route_batches(
    db: AsyncSession,
    *,
    total_distance_m: float | None,
    total_duration_s: float | None,
    batches,
    yandex_batches_by_number: dict[int, object],
    ordered_points=None,
    legs=None,
    geocoded_addresses=None,
) -> int:
    try:
        address_by_original_index = {
            address.original_index: address
            for address in (geocoded_addresses or [])
            if getattr(address, "id", None) is not None
        }
        start_address_id = _address_id_by_role(geocoded_addresses or [], "start")
        end_address_id = _address_id_by_role(geocoded_addresses or [], "end")

        result = await db.execute(
            text(
                """
                INSERT INTO route_jobs (
                    start_address_id,
                    end_address_id,
                    status,
                    total_distance_m,
                    total_duration_s,
                    finished_at
                )
                VALUES (
                    :start_address_id,
                    :end_address_id,
                    'completed',
                    :total_distance_m,
                    :total_duration_s,
                    now()
                )
                RETURNING id
                """
            ),
            {
                "start_address_id": start_address_id,
                "end_address_id": end_address_id,
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

        await _save_route_points(
            db,
            route_job_id=route_job_id,
            ordered_points=ordered_points or [],
            batches=batches,
            legs=legs or [],
            address_by_original_index=address_by_original_index,
        )

        await db.commit()
        return route_job_id
    except Exception:
        await db.rollback()
        raise


async def _save_route_points(
    db: AsyncSession,
    *,
    route_job_id: int,
    ordered_points,
    batches,
    legs,
    address_by_original_index: dict[int, object],
) -> None:
    if not ordered_points or not address_by_original_index:
        return

    batch_by_order = _batch_by_order(batches)
    leg_by_to_order = {leg.to_order: leg for leg in legs}

    for point in ordered_points:
        address = address_by_original_index.get(point.original_index)
        address_id = getattr(address, "id", None)
        if address_id is None:
            continue

        leg = leg_by_to_order.get(point.order)
        await db.execute(
            text(
                """
                INSERT INTO route_points (
                    route_job_id,
                    address_id,
                    original_order,
                    optimized_order,
                    batch_number,
                    is_start_point,
                    is_end_point,
                    distance_from_previous_m,
                    duration_from_previous_s
                )
                VALUES (
                    :route_job_id,
                    :address_id,
                    :original_order,
                    :optimized_order,
                    :batch_number,
                    :is_start_point,
                    :is_end_point,
                    :distance_from_previous_m,
                    :duration_from_previous_s
                )
                """
            ),
            {
                "route_job_id": route_job_id,
                "address_id": address_id,
                "original_order": point.original_index,
                "optimized_order": point.order,
                "batch_number": batch_by_order.get(point.order),
                "is_start_point": point.type == "start",
                "is_end_point": point.type == "end",
                "distance_from_previous_m": (
                    leg.distance_m if leg is not None else None
                ),
                "duration_from_previous_s": (
                    leg.duration_s if leg is not None else None
                ),
            },
        )


def _batch_by_order(batches) -> dict[int, int]:
    result: dict[int, int] = {}
    for batch in batches:
        for point in batch.points:
            if not point.is_transition_point:
                result[point.global_order] = batch.batch_number
    return result


def _address_id_by_role(addresses, role: str) -> int | None:
    for address in addresses:
        if address.role == role and address.id is not None:
            return address.id
    return None
