from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ..schemas.cinema import JadwalOut, KursiOut, PesanKursiIn, PesanKursiOut
from ..services.cinema_gateway import GatewayError, get_gateway

router = APIRouter(prefix="/api")


@router.get("/jadwal", response_model=list[JadwalOut])
def daftar_jadwal():
    try:
        return get_gateway().daftar_jadwal()
    except GatewayError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err


@router.get("/kursi", response_model=list[KursiOut])
def daftar_kursi(schedule_id: str):
    try:
        return get_gateway().daftar_kursi(schedule_id)
    except GatewayError as err:
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err


@router.post("/pesan", response_model=PesanKursiOut)
def pesan_kursi(payload: PesanKursiIn):
    try:
        return get_gateway().pesan_kursi(payload.schedule_id, payload.seat_ids)
    except GatewayError as err:
        # Business failure (kursi tidak tersedia) -> 409 Conflict.
        raise HTTPException(status_code=err.status_code, detail=err.detail) from err
