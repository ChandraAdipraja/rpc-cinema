"""Pydantic schemas (kontrak HTTP) sesuai shape proto tanpa detail grpc."""

from __future__ import annotations

from pydantic import BaseModel, Field


class JadwalOut(BaseModel):
    schedule_id: str
    judul: str
    genre: str
    durasi_menit: int
    jam_tayang: str


class KursiOut(BaseModel):
    id: str
    status: str  # "AVAILABLE" | "RESERVED"


class ReservationOut(BaseModel):
    reservation_id: str
    schedule_id: str
    seat_ids: list[str]
    status: str  # "AKTIF" | "DIBATALKAN"


class PesanKursiIn(BaseModel):
    schedule_id: str = Field(min_length=1)
    seat_ids: list[str] = Field(min_length=1)
    # Opsional: idempotency key dari client. Bila kosong, gateway membuat UUID.
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class BatalkanPesananIn(BaseModel):
    reservation_id: str = Field(min_length=1)
    # Opsional: idempotency key dari client. Bila kosong, gateway membuat UUID.
    request_id: str | None = Field(default=None, min_length=1, max_length=128)


class PesanKursiOut(BaseModel):
    success: bool
    message: str
    reservasi: ReservationOut | None = None
