"""Unit test IdempotencyStore: fingerprint, TTL, LRU, dan snapshot immutable."""

from __future__ import annotations

import pytest

from core.idempotency import (
    DEFAULT_MAX_ENTRIES,
    DEFAULT_TTL_SECONDS,
    MAX_ENTRIES_ENV_VAR,
    TTL_ENV_VAR,
    IdempotencyConflict,
    IdempotencyStore,
    OpResult,
    booking_fingerprint,
    cancel_fingerprint,
)
from core.storage import ReservationRecord

PESAN_OP = "pesan"
BATALKAN_OP = "batalkan"


class FakeClock:
    """Jam yang bisa dimajukan tanpa menunggu waktu nyata."""

    def __init__(self, start: float = 1_000.0) -> None:
        self.now = start

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


def _record(status: str = "ACTIVE") -> ReservationRecord:
    return ReservationRecord(
        reservation_id="res-1",
        schedule_id="s-1",
        seat_ids=("A1", "A2"),
        status=status,
        created_at=1.0,
    )


def _ok(reservation: ReservationRecord | None = None) -> OpResult:
    return OpResult(success=True, message="ok", reservation=reservation)


def _store(clock: FakeClock, **kwargs) -> IdempotencyStore:
    kwargs.setdefault("ttl_seconds", DEFAULT_TTL_SECONDS)
    return IdempotencyStore(clock=clock, **kwargs)


# -- Penyimpanan dan pengambilan -------------------------------------------


def test_save_dan_get_roundtrip():
    clock = FakeClock()
    store = _store(clock)
    fingerprint = booking_fingerprint(PESAN_OP, "s-1", ["A1"])

    store.save(PESAN_OP, "req-1", fingerprint, _ok(_record()))

    hasil = store.get(PESAN_OP, "req-1", fingerprint)
    assert hasil is not None
    assert hasil.success is True
    assert hasil.reservation is not None
    assert hasil.reservation.reservation_id == "res-1"
    assert len(store) == 1


def test_request_identik_menghasilkan_cache_hit():
    clock = FakeClock()
    store = _store(clock)
    fingerprint = booking_fingerprint(PESAN_OP, "s-1", ["A1", "A2"])
    store.save(PESAN_OP, "req-1", fingerprint, _ok(_record()))

    pertama = store.get(PESAN_OP, "req-1", fingerprint)
    kedua = store.get(PESAN_OP, "req-1", fingerprint)

    assert pertama is not None and kedua is not None
    assert pertama.reservation.reservation_id == kedua.reservation.reservation_id


def test_fingerprint_berbeda_ditolak():
    clock = FakeClock()
    store = _store(clock)
    store.save(PESAN_OP, "req-1", booking_fingerprint(PESAN_OP, "s-1", ["A1"]), _ok(_record()))

    with pytest.raises(IdempotencyConflict):
        store.get(PESAN_OP, "req-1", booking_fingerprint(PESAN_OP, "s-1", ["A2"]))


def test_operation_berbeda_tidak_saling_menimpa():
    clock = FakeClock()
    store = _store(clock)
    pesan_fp = booking_fingerprint(PESAN_OP, "s-1", ["A1"])
    batal_fp = cancel_fingerprint(BATALKAN_OP, "res-1")

    store.save(PESAN_OP, "req-1", pesan_fp, _ok(_record()))
    store.save(BATALKAN_OP, "req-1", batal_fp, _ok(_record("CANCELLED")))

    assert store.get(PESAN_OP, "req-1", pesan_fp).reservation.status == "ACTIVE"
    assert store.get(BATALKAN_OP, "req-1", batal_fp).reservation.status == "CANCELLED"


# -- Fingerprint ------------------------------------------------------------


def test_fingerprint_booking_konsisten_terhadap_urutan_kursi():
    satu = booking_fingerprint(PESAN_OP, "s-1", ["A2", "A1", "A3"])
    dua = booking_fingerprint(PESAN_OP, "s-1", ["A1", "A2", "A3"])
    assert satu == dua


def test_fingerprint_booking_berbeda_untuk_schedule_atau_kursi_berbeda():
    dasar = booking_fingerprint(PESAN_OP, "s-1", ["A1"])
    assert dasar != booking_fingerprint(PESAN_OP, "s-2", ["A1"])
    assert dasar != booking_fingerprint(PESAN_OP, "s-1", ["A2"])
    assert dasar != booking_fingerprint(BATALKAN_OP, "s-1", ["A1"])


def test_fingerprint_pembatalan_berbeda_per_reservation_id():
    satu = cancel_fingerprint(BATALKAN_OP, "res-1")
    dua = cancel_fingerprint(BATALKAN_OP, "res-2")
    assert satu != dua
    assert satu == cancel_fingerprint(BATALKAN_OP, "res-1")


def test_fingerprint_stabil_lintas_objek_baru():
    """SHA-256 atas payload kanonik, bukan hash() Python yang diacak per proses."""
    assert booking_fingerprint(PESAN_OP, "s-1", ["A1"]) == booking_fingerprint(
        PESAN_OP, "s-1", ["A1"]
    )
    # 64 karakter hex = SHA-256
    assert len(booking_fingerprint(PESAN_OP, "s-1", ["A1"])) == 64


# -- TTL --------------------------------------------------------------------


def test_default_ttl_adalah_24_jam(monkeypatch):
    monkeypatch.delenv(TTL_ENV_VAR, raising=False)
    store = IdempotencyStore(clock=FakeClock())
    assert store.ttl_seconds == DEFAULT_TTL_SECONDS == 24 * 60 * 60


def test_entri_masih_berlaku_sebelum_ttl():
    clock = FakeClock()
    store = _store(clock)
    fingerprint = booking_fingerprint(PESAN_OP, "s-1", ["A1"])
    store.save(PESAN_OP, "req-1", fingerprint, _ok(_record()))

    clock.advance(DEFAULT_TTL_SECONDS - 1)
    assert store.get(PESAN_OP, "req-1", fingerprint) is not None


def test_entri_kedaluwarsa_tidak_dapat_digunakan():
    clock = FakeClock()
    store = _store(clock)
    fingerprint = booking_fingerprint(PESAN_OP, "s-1", ["A1"])
    store.save(PESAN_OP, "req-1", fingerprint, _ok(_record()))

    clock.advance(DEFAULT_TTL_SECONDS + 1)

    assert store.get(PESAN_OP, "req-1", fingerprint) is None
    assert len(store) == 0  # entri expired ikut dibuang


def test_entri_kedaluwarsa_dibersihkan_saat_save_berikutnya():
    clock = FakeClock()
    store = _store(clock, ttl_seconds=10)
    lama = booking_fingerprint(PESAN_OP, "s-1", ["A1"])
    store.save(PESAN_OP, "lama", lama, _ok(_record()))

    clock.advance(11)
    store.save(PESAN_OP, "baru", booking_fingerprint(PESAN_OP, "s-1", ["A2"]), _ok(_record()))

    assert len(store) == 1
    assert store.get(PESAN_OP, "lama", lama) is None


# -- Kapasitas dan eviction -------------------------------------------------


def test_kapasitas_terbatas_dan_lru_eviction():
    clock = FakeClock()
    store = _store(clock, max_entries=2)
    fp1 = booking_fingerprint(PESAN_OP, "s-1", ["A1"])
    fp2 = booking_fingerprint(PESAN_OP, "s-1", ["A2"])
    fp3 = booking_fingerprint(PESAN_OP, "s-1", ["A3"])

    store.save(PESAN_OP, "req-1", fp1, _ok(_record()))
    store.save(PESAN_OP, "req-2", fp2, _ok(_record()))
    assert len(store) == 2

    # req-1 baru dipakai -> menjadi paling baru; req-2 jadi korban eviction.
    assert store.get(PESAN_OP, "req-1", fp1) is not None
    store.save(PESAN_OP, "req-3", fp3, _ok(_record()))

    assert len(store) == 2
    assert store.get(PESAN_OP, "req-1", fp1) is not None
    assert store.get(PESAN_OP, "req-2", fp2) is None
    assert store.get(PESAN_OP, "req-3", fp3) is not None


def test_default_max_entries(monkeypatch):
    monkeypatch.delenv(MAX_ENTRIES_ENV_VAR, raising=False)
    store = IdempotencyStore(clock=FakeClock())
    assert store.max_entries == DEFAULT_MAX_ENTRIES == 10_000


def test_env_override_ttl_dan_kapasitas(monkeypatch):
    monkeypatch.setenv(TTL_ENV_VAR, "60")
    monkeypatch.setenv(MAX_ENTRIES_ENV_VAR, "5")
    store = IdempotencyStore(clock=FakeClock())
    assert store.ttl_seconds == 60
    assert store.max_entries == 5


@pytest.mark.parametrize("value", ["abc", "0", "-3"])
def test_env_tidak_valid_ditolak(monkeypatch, value):
    monkeypatch.setenv(TTL_ENV_VAR, value)
    with pytest.raises(ValueError):
        IdempotencyStore(clock=FakeClock())


# -- Snapshot immutable -----------------------------------------------------


def test_cache_tidak_ikut_berubah_saat_record_asli_di_mutasi():
    clock = FakeClock()
    store = _store(clock)
    fingerprint = booking_fingerprint(PESAN_OP, "s-1", ["A1", "A2"])
    record = _record("ACTIVE")

    store.save(PESAN_OP, "req-1", fingerprint, _ok(record))
    # Simulasi CinemaState.cancel yang memutasi record hidup.
    record.status = "CANCELLED"

    hasil = store.get(PESAN_OP, "req-1", fingerprint)
    assert hasil.reservation.status == "ACTIVE"


def test_cache_tidak_menyerahkan_referensi_yang_dapat_dirusak_pemanggil():
    clock = FakeClock()
    store = _store(clock)
    fingerprint = booking_fingerprint(PESAN_OP, "s-1", ["A1"])
    store.save(PESAN_OP, "req-1", fingerprint, _ok(_record()))

    pertama = store.get(PESAN_OP, "req-1", fingerprint)
    pertama.reservation.status = "CANCELLED"

    kedua = store.get(PESAN_OP, "req-1", fingerprint)
    assert kedua.reservation.status == "ACTIVE"
