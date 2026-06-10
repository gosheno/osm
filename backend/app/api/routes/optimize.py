from fastapi import APIRouter, HTTPException

from app.clients.osrm_client import OsrmError, OsrmNoRouteError, OsrmUnavailableError
from app.schemas.optimization import OptimizeRouteRequest, OptimizeRouteResponse
from app.services.route_optimizer import (
    InvalidMatrixError,
    RouteOptimizationError,
    TooManyPointsError,
    UnreachableRouteError,
    build_optimized_route,
)


router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/optimize-coordinates", response_model=OptimizeRouteResponse)
async def optimize_coordinates(payload: OptimizeRouteRequest):
    try:
        return await build_optimized_route(payload)
    except TooManyPointsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OsrmUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"OSRM is not available: {exc}")
    except OsrmNoRouteError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"OSRM table calculation failed: {exc}",
        )
    except UnreachableRouteError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except InvalidMatrixError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OsrmError as exc:
        raise HTTPException(
            status_code=503,
            detail=f"OSRM table calculation failed: {exc}",
        )
    except RouteOptimizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Route optimization failed: {exc}",
        )
