"""Request ID deduplication untuk operasi yang mengubah state.

Setiap operasi logis (pesan/batalkan) membawa request_id yang unik. Server
menyimpan hasil operasi berdasarkan (op, request_id) beserta fingerprint
payload; permintaan ulang dengan ID yang sama dan payload identik
mengembalikan hasil sebelumnya tanpa memproses lagi, sedangkan ID yang sama
dengan payload berbeda ditolak.

Kebijakan penyimpanan:

- TTL default 24 jam (``IDEMPOTENCY_TTL_SECONDS``). Entri yang sudah
  kedaluwarsa tidak pernah dipakai sebagai cache dan dibuang saat diakses.
- Kapasitas default 10.000 entri (``IDEMPOTENCY_MAX_ENTRIES``). Bila penuh,
  entri yang paling lama tidak dipakai (LRU) dibuang lebih dulu.
- Hanya hasil operasi yang benar-benar mengubah state (atau hasil sukses)
  yang disimpan; lihat ``CinemaService`` untuk kebijakan per jalur.

Atomicity check -> mutasi state -> simpan hasil tetap dijamin oleh
``StateLock`` server. Lock internal di store hanya melindungi integritas
struktur data bila store dipakai langsung; urutan lock selalu
``StateLock -> lock store`` sehingga tidak ada jalur deadlock.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
import typing
from collections import OrderedDict
from dataclasses import dataclass, replace

from .storage import ReservationRecord

DEFAULT_TTL_SECONDS = 24 * 60 * 60
DEFAULT_MAX_ENTRIES = 10_000

TTL_ENV_VAR = "IDEMPOTENCY_TTL_SECONDS"
MAX_ENTRIES_ENV_VAR = "IDEMPOTENCY_MAX_ENTRIES"


@dataclass(frozen=True)
class OpResult:
    """Hasil satu operasi logis yang dipakai ulang saat retry.

    ``reservation`` selalu berupa salinan bebas (snapshot), bukan referensi
    ke record yang masih dipakai ``CinemaState``.
    """

    success: bool
    message: str
    reservation: typing.Optional[ReservationRecord] = None


@dataclass(frozen=True)
class _Entry:
    fingerprint: str
    result: OpResult
    created_at: float


class IdempotencyConflict(Exception):
    """request_id sudah dipakai untuk operasi dengan payload berbeda."""


def _digest(op: str, **fields: object) -> str:
    """Fingerprint deterministik (SHA-256) atas payload terstruktur."""
    payload = json.dumps(
        {"op": op, **fields},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def booking_fingerprint(op: str, schedule_id: str, seat_ids: typing.Sequence[str]) -> str:
    """Fingerprint booking; urutan kursi tidak memengaruhi hasil.

    Booking bersifat himpunan kursi (all-or-nothing), jadi ``seat_ids``
    dinormalisasi dengan pengurutan agar permintaan yang sama dengan urutan
    berbeda tetap dianggap identik.
    """
    return _digest(op, schedule_id=schedule_id, seat_ids=sorted(seat_ids))


def cancel_fingerprint(op: str, reservation_id: str) -> str:
    """Fingerprint pembatalan; hanya reservation_id yang relevan."""
    return _digest(op, reservation_id=reservation_id)


def _require_positive(value: int, name: str) -> int:
    if value <= 0:
        raise ValueError(f"{name} harus bilangan bulat positif, diterima: {value!r}")
    return value


def _env_positive_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        parsed = int(raw)
    except ValueError as err:
        raise ValueError(
            f"{name} harus bilangan bulat positif, diterima: {raw!r}"
        ) from err
    return _require_positive(parsed, name)


def _copy_result(result: OpResult) -> OpResult:
    """Salinan hasil operasi; record reservasi tidak dibagi dengan state."""
    if result.reservation is None:
        return result
    return OpResult(
        success=result.success,
        message=result.message,
        reservation=replace(result.reservation),
    )


class IdempotencyStore:
    def __init__(
        self,
        ttl_seconds: typing.Optional[int] = None,
        max_entries: typing.Optional[int] = None,
        clock: typing.Callable[[], float] = time.monotonic,
    ) -> None:
        # None berarti "ambil dari environment" agar server tetap bisa
        # dikonfigurasi tanpa mengubah composition root.
        self._ttl_seconds = (
            _env_positive_int(TTL_ENV_VAR, DEFAULT_TTL_SECONDS)
            if ttl_seconds is None
            else _require_positive(ttl_seconds, TTL_ENV_VAR)
        )
        self._max_entries = (
            _env_positive_int(MAX_ENTRIES_ENV_VAR, DEFAULT_MAX_ENTRIES)
            if max_entries is None
            else _require_positive(max_entries, MAX_ENTRIES_ENV_VAR)
        )
        self._clock = clock
        self._results: OrderedDict[tuple[str, str], _Entry] = OrderedDict()
        self._lock = threading.Lock()

    @property
    def ttl_seconds(self) -> int:
        return self._ttl_seconds

    @property
    def max_entries(self) -> int:
        return self._max_entries

    def get(
        self,
        op: str,
        request_id: str,
        fingerprint: str,
    ) -> typing.Optional[OpResult]:
        """Ambil hasil cache; None bila tidak ada atau sudah kedaluwarsa.

        Raises:
            IdempotencyConflict: entri ada, masih berlaku, tetapi fingerprint
                berbeda (request_id dipakai ulang untuk payload lain).
        """
        key = (op, request_id)
        with self._lock:
            entry = self._results.get(key)
            if entry is None:
                return None
            if self._is_expired(entry, self._clock()):
                del self._results[key]
                return None
            if entry.fingerprint != fingerprint:
                raise IdempotencyConflict(
                    f"request_id {request_id!r} sudah dipakai untuk operasi {op!r} "
                    "dengan payload berbeda"
                )
            self._results.move_to_end(key)
            return _copy_result(entry.result)

    def save(
        self,
        op: str,
        request_id: str,
        fingerprint: str,
        result: OpResult,
    ) -> None:
        """Simpan hasil operasi beserta fingerprint dan timestamp."""
        entry = _Entry(
            fingerprint=fingerprint,
            result=_copy_result(result),
            created_at=self._clock(),
        )
        key = (op, request_id)
        with self._lock:
            self._purge_expired(self._clock())
            self._results[key] = entry
            self._results.move_to_end(key)
            while len(self._results) > self._max_entries:
                # LRU: entri paling lama tidak dipakai dibuang lebih dulu.
                self._results.popitem(last=False)

    def __len__(self) -> int:
        with self._lock:
            return len(self._results)

    def _is_expired(self, entry: _Entry, now: float) -> bool:
        return now - entry.created_at >= self._ttl_seconds

    def _purge_expired(self, now: float) -> None:
        expired = [
            key for key, entry in self._results.items() if self._is_expired(entry, now)
        ]
        for key in expired:
            del self._results[key]
