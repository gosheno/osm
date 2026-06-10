from fastapi import APIRouter, HTTPException

from app.schemas.batching import BatchRouteRequest, BatchRouteResponse
from app.services.route_batching import (
    InvalidBatchSizeError,
    InvalidLegsError,
    InvalidOrderedPointsError,
    RouteBatchingError,
    batch_optimized_route,
)


router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/batch", response_model=BatchRouteResponse)
def batch_route(payload: BatchRouteRequest):
    try:
        return batch_optimized_route(payload)
    except (InvalidBatchSizeError, InvalidOrderedPointsError, InvalidLegsError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except RouteBatchingError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Route batching failed: {exc}")
