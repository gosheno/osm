from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.address import (
    AddressBulkNormalizeItem,
    AddressBulkNormalizeRequest,
    AddressBulkNormalizeResponse,
    AddressGeocodeRequest,
    AddressGeocodeResponse,
    AddressNormalizeRequest,
    AddressNormalizeResponse,
)
from app.services.address_service import AddressService
from app.utils.address_normalizer import normalize_address


router = APIRouter(prefix="/api/addresses", tags=["addresses"])


@router.post("/normalize", response_model=AddressNormalizeResponse)
def normalize_single_address(payload: AddressNormalizeRequest):
    try:
        result = normalize_address(
            payload.address,
            default_city=payload.default_city,
            place_name=payload.place_name,
        )

        return AddressNormalizeResponse(
            original_address=result.original_address,
            address_for_geocoding=result.address_for_geocoding,
            normalized_address=result.normalized_address,
            tokens=result.tokens,
            place_name=result.place_name,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/normalize/bulk", response_model=AddressBulkNormalizeResponse)
def normalize_bulk_addresses(payload: AddressBulkNormalizeRequest):
    items: list[AddressBulkNormalizeItem] = []

    for address in payload.addresses:
        try:
            result = normalize_address(
                address,
                default_city=payload.default_city,
            )

            items.append(
                AddressBulkNormalizeItem(
                    original_address=result.original_address,
                    address_for_geocoding=result.address_for_geocoding,
                    normalized_address=result.normalized_address,
                    tokens=result.tokens,
                    place_name=result.place_name,
                    status="ok",
                )
            )
        except ValueError as exc:
            items.append(
                AddressBulkNormalizeItem(
                    original_address=address,
                    status="error",
                    error=str(exc),
                )
            )

    return AddressBulkNormalizeResponse(
        total=len(items),
        items=items,
    )


@router.post("/geocode", response_model=AddressGeocodeResponse)
async def geocode_address(
    payload: AddressGeocodeRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = AddressService(db)
        result = await service.geocode_address(
            address=payload.address,
            default_city=payload.default_city,
            place_name=payload.place_name,
            force_refresh=payload.force_refresh,
        )

        return AddressGeocodeResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Geocoding failed: {exc}",
        )
