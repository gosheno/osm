from collections.abc import Sequence
from typing import Any

import httpx

from app.core.config import settings


CoordinatePair = tuple[float, float]
MAX_OSRM_POINTS = 100
OSRM_SNAP_RADIUS_METERS = 1000
HEALTH_CHECK_POINTS: tuple[CoordinatePair, CoordinatePair] = (
    (59.9398, 30.3141),
    (59.9297, 30.3627),
)


class OsrmError(Exception):
    pass


class OsrmNoRouteError(OsrmError):
    pass


class OsrmUnavailableError(OsrmError):
    pass


class OsrmUnexpectedResponseError(OsrmError):
    pass


class OsrmClient:
    def __init__(self) -> None:
        self.base_url = settings.osrm_base_url.rstrip("/")

    async def check_health(self) -> dict[str, Any]:
        return await self._get(
            f"/route/v1/driving/{format_coordinates_for_osrm(HEALTH_CHECK_POINTS)}",
            params={
                "overview": "false",
                "steps": "false",
                "radiuses": format_osrm_radiuses(HEALTH_CHECK_POINTS),
            },
        )

    async def check_osrm(self) -> dict[str, Any]:
        return await self.check_health()

    async def get_route(
        self,
        points: Sequence[Any],
        *,
        overview: bool = True,
        steps: bool = False,
    ) -> dict[str, Any]:
        coordinates = format_coordinates_for_osrm(points)
        data = await self._get(
            f"/route/v1/driving/{coordinates}",
            params={
                "overview": "full" if overview else "false",
                "geometries": "geojson",
                "steps": str(steps).lower(),
                "alternatives": "false",
                "radiuses": format_osrm_radiuses(points),
            },
        )

        routes = data.get("routes")
        if not isinstance(routes, list) or not routes:
            raise OsrmNoRouteError("OSRM returned no routes")

        route = routes[0]
        if not isinstance(route, dict):
            raise OsrmUnexpectedResponseError("OSRM returned an invalid route")

        return {
            "code": data.get("code"),
            "distance_m": _required_float(route, "distance"),
            "duration_s": _required_float(route, "duration"),
            "geometry": route.get("geometry"),
            "waypoints": _normalize_waypoints(data.get("waypoints")),
        }

    async def get_table(
        self,
        points: Sequence[Any],
        *,
        annotations: str = "duration,distance",
        max_points: int = MAX_OSRM_POINTS,
    ) -> dict[str, Any]:
        coordinates = format_coordinates_for_osrm(points, max_points=max_points)
        data = await self._get(
            f"/table/v1/driving/{coordinates}",
            params={
                "annotations": annotations,
                "radiuses": format_osrm_radiuses(points, max_points=max_points),
            },
        )

        return {
            "code": data.get("code"),
            "durations": _matrix(data.get("durations")),
            "distances": _matrix(data.get("distances")),
            "sources": _normalize_waypoints(data.get("sources")),
            "destinations": _normalize_waypoints(data.get("destinations")),
        }

    async def get_duration_matrix(self, points: Sequence[Any]) -> list[list[float | None]]:
        table = await self.get_table(points, annotations="duration")
        return table["durations"]

    async def get_distance_matrix(self, points: Sequence[Any]) -> list[list[float | None]]:
        table = await self.get_table(points, annotations="distance")
        return table["distances"]

    async def nearest(
        self,
        *,
        latitude: float,
        longitude: float,
        profile: str = "driving",
        number: int = 1,
    ) -> dict[str, Any]:
        return await self._get(
            f"/nearest/v1/{profile}/{longitude},{latitude}",
            params={"number": number},
        )

    async def route(
        self,
        *,
        points: Sequence[CoordinatePair],
        profile: str = "driving",
        steps: bool = True,
        overview: str = "full",
        geometries: str = "geojson",
    ) -> dict[str, Any]:
        coordinates = format_coordinates_for_osrm(points)

        return await self._get(
            f"/route/v1/{profile}/{coordinates}",
            params={
                "steps": str(steps).lower(),
                "overview": overview,
                "geometries": geometries,
                "alternatives": "false",
                "radiuses": format_osrm_radiuses(points),
            },
        )

    async def _get(
        self,
        path: str,
        *,
        params: dict[str, Any],
    ) -> dict[str, Any]:
        try:
            async with httpx.AsyncClient(timeout=20.0) as client:
                response = await client.get(f"{self.base_url}{path}", params=params)
        except httpx.TimeoutException as exc:
            raise OsrmUnavailableError("OSRM request timed out") from exc
        except httpx.RequestError as exc:
            raise OsrmUnavailableError(f"OSRM request failed: {exc}") from exc

        try:
            data = response.json()
        except ValueError as exc:
            raise OsrmUnexpectedResponseError(
                "OSRM returned a non-JSON response"
            ) from exc

        if not isinstance(data, dict):
            raise OsrmUnexpectedResponseError(
                f"OSRM returned unexpected response type: {type(data).__name__}"
            )

        code = data.get("code")
        if code != "Ok":
            message = data.get("message") or code or "OSRM request failed"
            if code in {"NoRoute", "NoSegment"}:
                raise OsrmNoRouteError(f"{code}: {message}")
            if response.status_code != 200:
                raise OsrmError(
                    f"OSRM returned HTTP {response.status_code}: {message}"
                )
            raise OsrmError(f"{code}: {message}" if code else message)

        if response.status_code != 200:
            raise OsrmError(f"OSRM returned HTTP {response.status_code}")

        return data


def validate_points(
    points: Sequence[Any],
    *,
    min_points: int = 2,
    max_points: int = MAX_OSRM_POINTS,
) -> list[CoordinatePair]:
    normalized = [_coordinate_pair(point) for point in points]

    if len(normalized) < min_points:
        raise ValueError(f"At least {min_points} points are required")

    if len(normalized) > max_points:
        raise ValueError(f"At most {max_points} points are allowed")

    return normalized


def format_coordinates_for_osrm(
    points: Sequence[Any],
    *,
    max_points: int = MAX_OSRM_POINTS,
) -> str:
    return ";".join(
        f"{longitude},{latitude}"
        for latitude, longitude in validate_points(points, max_points=max_points)
    )


def format_osrm_radiuses(
    points: Sequence[Any],
    *,
    max_points: int = MAX_OSRM_POINTS,
) -> str:
    return ";".join(
        str(OSRM_SNAP_RADIUS_METERS)
        for _ in validate_points(points, max_points=max_points)
    )


def _coordinate_pair(point: Any) -> CoordinatePair:
    if isinstance(point, dict):
        latitude = point.get("latitude")
        longitude = point.get("longitude")
    elif isinstance(point, (list, tuple)) and len(point) == 2:
        latitude, longitude = point
    else:
        latitude = getattr(point, "latitude", None)
        longitude = getattr(point, "longitude", None)

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except (TypeError, ValueError) as exc:
        raise ValueError("Point must contain numeric latitude and longitude") from exc

    if not -90 <= latitude <= 90:
        raise ValueError("Latitude must be between -90 and 90")

    if not -180 <= longitude <= 180:
        raise ValueError("Longitude must be between -180 and 180")

    return latitude, longitude


def _normalize_waypoints(items: Any) -> list[dict[str, Any]]:
    if not isinstance(items, list):
        return []

    waypoints: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue

        location = item.get("location")
        if not isinstance(location, list) or len(location) < 2:
            continue

        waypoint: dict[str, Any] = {
            "latitude": float(location[1]),
            "longitude": float(location[0]),
            "name": item.get("name") or None,
        }

        if item.get("distance") is not None:
            waypoint["distance_m"] = float(item["distance"])

        waypoints.append(waypoint)

    return waypoints


def _matrix(value: Any) -> list[list[float | None]]:
    if not isinstance(value, list):
        return []

    matrix: list[list[float | None]] = []
    for row in value:
        if not isinstance(row, list):
            continue

        matrix.append(
            [
                float(cell) if cell is not None else None
                for cell in row
            ]
        )

    return matrix


def _required_float(value: dict[str, Any], key: str) -> float:
    raw = value.get(key)
    if raw is None:
        raise OsrmUnexpectedResponseError(f"OSRM route is missing {key}")

    try:
        return float(raw)
    except (TypeError, ValueError) as exc:
        raise OsrmUnexpectedResponseError(
            f"OSRM route returned invalid {key}: {raw}"
        ) from exc
