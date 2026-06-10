from fastapi import APIRouter, HTTPException

from app.clients.osrm_client import OsrmError, OsrmNoRouteError, OsrmUnavailableError
from app.schemas.osrm import (
    OsrmHealthResponse,
    OsrmRouteRequest,
    OsrmRouteResponse,
    OsrmTableRequest,
    OsrmTableResponse,
)


router = APIRouter(prefix="/api", tags=["osrm"])


def _client():
    from app.clients.osrm_client import OsrmClient

    return OsrmClient()


@router.get("/health/osrm", response_model=OsrmHealthResponse)
async def health_osrm():
    try:
        data = await _client().check_health()
        return {
            "status": "ok",
            "service": "osrm",
            "code": data.get("code", "Ok"),
        }
    except OsrmUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"OSRM is not available: {exc}",
        )
    except OsrmError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"OSRM health check failed: {exc}",
        )


@router.post("/osrm/route", response_model=OsrmRouteResponse)
async def osrm_route(payload: OsrmRouteRequest):
    try:
        return await _client().get_route(
            payload.points,
            overview=payload.overview,
            steps=payload.steps,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OsrmNoRouteError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"OSRM route calculation failed: {exc}",
        )
    except OsrmUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"OSRM route calculation failed: {exc}",
        )
    except OsrmError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OSRM route calculation failed: {exc}",
        )


@router.post("/osrm/table", response_model=OsrmTableResponse)
async def osrm_table(payload: OsrmTableRequest):
    try:
        return await _client().get_table(payload.points)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    except OsrmNoRouteError as exc:
        raise HTTPException(
            status_code=404,
            detail=f"OSRM table calculation failed: {exc}",
        )
    except OsrmUnavailableError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"OSRM table calculation failed: {exc}",
        )
    except OsrmError as exc:
        raise HTTPException(
            status_code=502,
            detail=f"OSRM table calculation failed: {exc}",
        )
