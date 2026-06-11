from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.osrm_client import OsrmError, OsrmNoRouteError, OsrmUnavailableError
from app.core.exceptions import AppError, BatchingAppError, OptimizationAppError, OsrmAppError, YandexLinkAppError
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
        raise OptimizationAppError(
            code="OPTIMIZATION_TOO_MANY_POINTS",
            message="Слишком много точек для MVP-алгоритма.",
            details=str(exc),
            status_code=400,
        )
    except (InvalidBatchSizeError, InvalidOrderedPointsError, InvalidLegsError) as exc:
        raise BatchingAppError(
            code="BATCHING_INVALID_ORDERED_POINTS",
            message="Невозможно разбить маршрут на пакеты: некорректный порядок точек.",
            details=str(exc),
            status_code=400,
        )
    except YandexLinkValidationError as exc:
        raise YandexLinkAppError(
            code="YANDEX_LINK_FAILED",
            message="Не удалось сформировать ссылку Яндекс.Карт.",
            details=str(exc),
            status_code=400,
        )
    except UnreachableRouteError as exc:
        raise OptimizationAppError(
            code="OPTIMIZATION_FAILED",
            message="Не удалось оптимизировать порядок точек.",
            details=str(exc),
            status_code=400,
        )
    except OsrmUnavailableError as exc:
        raise OsrmAppError(
            code="OSRM_UNAVAILABLE",
            message="Сервис построения маршрутов OSRM недоступен. Проверьте, запущен ли контейнер osrm.",
            details=str(exc),
            status_code=503,
        )
    except OsrmNoRouteError as exc:
        raise OsrmAppError(
            code="OSRM_NO_ROUTE",
            message="Между некоторыми точками не удалось построить автомобильный маршрут.",
            details=str(exc),
            status_code=503,
        )
    except InvalidMatrixError as exc:
        raise OptimizationAppError(
            code="OPTIMIZATION_MATRIX_INVALID",
            message="Невозможно оптимизировать маршрут из-за некорректной матрицы расстояний.",
            details=str(exc),
            status_code=503,
        )
    except OsrmError as exc:
        raise OsrmAppError(
            code="OSRM_ROUTE_FAILED",
            message="OSRM не смог построить маршрут.",
            details=str(exc),
            status_code=503,
        )
    except (RoutePipelineError, RouteBatchingError, YandexLinkError) as exc:
        raise AppError(
            code="ROUTE_PROCESSING_FAILED",
            message="Не удалось построить маршрут.",
            details=str(exc),
            status_code=400,
        )
    except RouteOptimizationError as exc:
        raise OptimizationAppError(
            code="OPTIMIZATION_FAILED",
            message="Не удалось оптимизировать порядок точек.",
            details=str(exc),
            status_code=400,
        )
    except AppError:
        raise
    except Exception as exc:
        raise AppError(
            code="INTERNAL_SERVER_ERROR",
            message="Произошла внутренняя ошибка сервера.",
            details=str(exc),
            status_code=500,
        )
