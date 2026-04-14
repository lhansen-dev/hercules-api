from fastapi import APIRouter, HTTPException, status

from hercules_api.deps import OFFDep, SessionDep, USDADep
from hercules_api.schemas.food import (
    BarcodeLookupRequest,
    BarcodeScanRequest,
    FoodOut,
    FoodSearchRequest,
)
from hercules_api.services.barcode_decode import BarcodeDecodeError, decode_barcode_from_base64
from hercules_api.services.food_resolver import lookup_barcode, search_foods

router = APIRouter(prefix="/foods", tags=["foods"])


@router.post("/search", response_model=list[FoodOut])
async def search_food(
    req: FoodSearchRequest,
    session: SessionDep,
    off: OFFDep,
    usda: USDADep,
) -> list[FoodOut]:
    results = await search_foods(session, req.query, req.limit, off, usda)
    return [FoodOut.model_validate(f) for f in results]


@router.post("/barcode", response_model=FoodOut)
async def lookup_barcode_endpoint(
    req: BarcodeLookupRequest,
    session: SessionDep,
    off: OFFDep,
    usda: USDADep,
) -> FoodOut:
    food = await lookup_barcode(session, req.barcode, off, usda)
    if not food:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No food found for barcode {req.barcode}",
        )
    return FoodOut.model_validate(food)


@router.post("/barcode/scan", response_model=FoodOut)
async def scan_barcode_endpoint(
    req: BarcodeScanRequest,
    session: SessionDep,
    off: OFFDep,
    usda: USDADep,
) -> FoodOut:
    try:
        barcode = decode_barcode_from_base64(req.image_base64)
    except BarcodeDecodeError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(e)
        ) from e

    food = await lookup_barcode(session, barcode, off, usda)
    if not food:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Decoded barcode {barcode} but no matching food found.",
        )
    return FoodOut.model_validate(food)
