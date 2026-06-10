from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.osrm_client import OsrmError, OsrmNoRouteError, OsrmUnavailableError
from app.db.session import get_db
from app.schemas.route import (
    OptimizeRouteByAddressesRequest,
    OptimizeRouteByAddressesResponse,
)
from app.services.route_batching import (
    InvalidBatchSizeError,
    InvalidLegsError,
    InvalidOrderedPointsError,
    RouteBatchingError,
)
from app.services.route_optimizer import (
    InvalidMatrixError,
    RouteOptimizationError,
    TooManyPointsError,
    UnreachableRouteError,
)
from app.services.route_pipeline import RoutePipelineError, optimize_route_by_addresses
from app.services.yandex_link_builder import YandexLinkError, YandexLinkValidationError


router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/optimize", response_model=OptimizeRouteByAddressesResponse)
async def optimize_route(
    payload: OptimizeRouteByAddressesRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        return await optimize_route_by_addresses(payload, db)
    except TooManyPointsError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except (InvalidBatchSizeError, InvalidOrderedPointsError, InvalidLegsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YandexLinkValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except UnreachableRouteError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except OsrmUnavailableError as exc:
        raise HTTPException(status_code=503, detail=f"OSRM is not available: {exc}")
    except OsrmNoRouteError as exc:
        raise HTTPException(status_code=503, detail=f"OSRM route calculation failed: {exc}")
    except InvalidMatrixError as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except OsrmError as exc:
        raise HTTPException(status_code=503, detail=f"OSRM route calculation failed: {exc}")
    except (RoutePipelineError, RouteBatchingError, YandexLinkError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RouteOptimizationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Route optimization failed: {exc}")
