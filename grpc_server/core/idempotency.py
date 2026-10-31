"""Request ID deduplication untuk operasi yang mengubah state.

Setiap operasi logis (pesan/batalkan) membawa request_id yang unik.
Server menyimpan hasil operasi berdasarkan (op, request_id); permintaan
ulang dengan ID yang sama mengembalikan hasil sebelumnya tanpa memproses
lagi. Penyimpanan dilindungi lock yang sama dengan state agar pencatatan
hasil dan mutasi state berjalan satu kesatuan.
"""

from __future__ import annotations

import typing
from dataclasses import dataclass

from .storage import ReservationRecord


@dataclass
class OpResult:
    """Hasil satu operasi logis yang dipakai ulang saat retry."""

    success: bool
    message: str
    reservation: typing.Optional[ReservationRecord] = None


class IdempotencyStore:
    def __init__(self) -> None:
        # Akses seluruh data harus dilakukan sambil memegang StateLock server,
        # sehingga check dan pencatatan hasil berada di critical section yang sama.
        self._results: dict[tuple[str, str], OpResult] = {}

    def get(self, op: str, request_id: str) -> typing.Optional[OpResult]:
        return self._results.get((op, request_id))

    def save(self, op: str, request_id: str, result: OpResult) -> None:
        self._results[(op, request_id)] = result
