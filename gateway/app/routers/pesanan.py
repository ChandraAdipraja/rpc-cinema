from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.cinema import BatalkanPesananIn, ReservationOut
from ..services.cinema_gateway import GatewayError, get_gateway

router = APIRouter(prefix="/api")


@router.post("/batal")
def batalkan_pesanan(payload: BatalkanPesananIn):
    try:
        return get_gateway().batalkan_pesanan(
            payload.reservation_id,
            payload.request_id,
        )
    except GatewayError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err


@router.get("/pesanan/{reservation_id}", response_model=ReservationOut)
def detail_pesanan(reservation_id: str):
    try:
        return get_gateway().detail_pesanan(reservation_id)
    except GatewayError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err
