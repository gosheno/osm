from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.schemas.address import (
    AddressBulkNormalizeItem,
    AddressBulkNormalizeRequest,
    AddressBulkNormalizeResponse,
    AddressConfirmRequest,
    AddressConfirmResponse,
    AddressGeocodeRequest,
    AddressGeocodeResponse,
    AddressNormalizeRequest,
    AddressNormalizeResponse,
    AddressSuggestResponse,
)
from app.services.address_service import AddressService
from app.services.gar_normalizer import GarAddressNormalizer
from app.services.address_suggestions import (
    AddressSuggestQueryTooShortError,
    AddressSuggestionService,
)
from app.utils.address_normalizer import normalize_address


router = APIRouter(prefix="/api/addresses", tags=["addresses"])


@router.post("/normalize", response_model=AddressNormalizeResponse)
async def normalize_single_address(
    payload: AddressNormalizeRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        result = normalize_address(
            payload.address,
            default_city=payload.default_city,
            place_name=payload.place_name,
        )

        response = AddressNormalizeResponse(
            original_address=result.original_address,
            address_for_geocoding=result.address_for_geocoding,
            normalized_address=result.normalized_address,
            tokens=result.tokens,
            place_name=result.place_name,
        )

        if payload.use_gar:
            try:
                gar_result = await GarAddressNormalizer(db).normalize(
                    payload.address,
                    region_hint=payload.region_hint,
                    city_hint=payload.city_hint,
                )
                response.status = gar_result.status
                response.normalized_full_address = gar_result.normalized_full_address
                response.region = gar_result.region
                response.city = gar_result.city
                response.settlement = gar_result.settlement
                response.district = gar_result.district
                response.street = gar_result.street
                response.house = gar_result.house
                response.building = gar_result.building
                response.structure = gar_result.structure
                response.postcode = gar_result.postcode
                response.gar_object_id = gar_result.gar_object_id
                response.gar_house_id = gar_result.gar_house_id
                response.fias_id = gar_result.fias_id
                response.confidence = gar_result.confidence
                response.comment = gar_result.comment
                response.variants = gar_result.variants
            except Exception as exc:
                response.comment = f"GAR/FIAS normalization is unavailable: {exc}"

        return response
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


@router.get("/suggest", response_model=AddressSuggestResponse)
async def suggest_addresses(
    query: str,
    limit: int = 5,
    lang: str = "ru",
    bounded: bool | None = None,
    viewbox: str | None = None,
    context_city: str | None = None,
    context_region: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = AddressSuggestionService(db)
        normalized_query, items = await service.suggest(
            query=query,
            limit=limit,
            lang=lang,
            bounded=bounded,
            viewbox=viewbox,
            context_city=context_city,
            context_region=context_region,
        )
        return AddressSuggestResponse(
            query=query,
            normalized_query=normalized_query,
            status="ok",
            items=items,
        )
    except AddressSuggestQueryTooShortError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Address suggestions failed: {exc}",
        )


@router.post("/confirm", response_model=AddressConfirmResponse)
async def confirm_address(
    payload: AddressConfirmRequest,
    db: AsyncSession = Depends(get_db),
):
    try:
        service = AddressSuggestionService(db)
        result = await service.confirm(
            original_query=payload.original_query,
            selected_candidate=payload.selected_candidate,
        )
        return AddressConfirmResponse(
            status="saved",
            address_id=result["id"],
            latitude=result["latitude"],
            longitude=result["longitude"],
            geocoding_status=result["geocoding_status"],
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Address confirmation failed: {exc}",
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
            geocoding_context=payload.geocoding_context,
            geocoding_area=payload.geocoding_area,
        )

        return AddressGeocodeResponse(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(
            status_code=503,
            detail=f"Geocoding failed: {exc}",
        )
