from fastapi import APIRouter, HTTPException

from app.schemas.yandex_links import (
    BuildYandexLinksRequest,
    BuildYandexLinksResponse,
)
from app.services.yandex_link_builder import (
    YandexLinkError,
    YandexLinkValidationError,
    add_yandex_links_to_batches,
)


router = APIRouter(prefix="/api/routes", tags=["routes"])


@router.post("/yandex-links", response_model=BuildYandexLinksResponse)
def build_yandex_links(payload: BuildYandexLinksRequest):
    try:
        return add_yandex_links_to_batches(payload)
    except YandexLinkValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except YandexLinkError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Yandex link generation failed: {exc}",
        )
