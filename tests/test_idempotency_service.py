"""Test integrasi CinemaService <-> IdempotencyStore tanpa transport gRPC.

Memakai CinemaState asli, StateLock asli, dan context palsu sehingga
pemanggilan mutasi (reserve/cancel) bisa dihitung untuk membuktikan retry
tidak mengulang efek samping.
"""

from __future__ import annotations

import grpc
import pytest

from core.idempotency import IdempotencyStore
from core.locking import StateLock
from core.storage import CinemaState, Schedule
from services.cinema_service import CinemaService
from stubs import cinema_pb2

SID = "s-1"
SID2 = "s-2"
SEATS = ("A1", "A2", "A3")


class AbortError(Exception):
    def __init__(self, code, details: str) -> None:
        super().__init__(details)
        self.code = code
        self.details = details


class FakeContext:
    """Context minimal: abort melempar seperti ServicerContext sungguhan."""

    def abort(self, code, details: str) -> None:
        raise AbortError(code, details)


class CountingState:
    """Delegasi ke CinemaState sambil menghitung pemanggilan mutasi."""

    def __init__(self, state: CinemaState) -> None:
        self._state = state
        self.reserve_calls = 0
        self.cancel_calls = 0

    def reserve(self, schedule_id, seat_ids):
        self.reserve_calls += 1
        return self._state.reserve(schedule_id, seat_ids)

    def cancel(self, reservation_id):
        self.cancel_calls += 1
        return self._state.cancel(reservation_id)

    def __getattr__(self, name):
        return getattr(self._state, name)


def _build() -> tuple[CinemaService, CountingState, CinemaState, IdempotencyStore]:
    state_lock = StateLock()
    state = CinemaState(
        lock=state_lock.rlock,
        schedules=[
            Schedule(SID, "Film Satu", "Drama", 100, "10:00"),
            Schedule(SID2, "Film Dua", "Komedi", 90, "13:00"),
        ],
        seat_ids=SEATS,
    )
    counting = CountingState(state)
    store = IdempotencyStore()
    service = CinemaService(state=counting, idempotency=store, state_lock=state_lock)
    return service, counting, state, store


def _pesan(request_id: str, seat_ids, schedule_id: str = SID):
    return cinema_pb2.PesanKursiRequest(
        request_id=request_id,
        schedule_id=schedule_id,
        seat_ids=list(seat_ids),
    )


def _batal(request_id: str, reservation_id: str):
    return cinema_pb2.BatalkanPesananRequest(
        request_id=request_id,
        reservation_id=reservation_id,
    )


def _status(state: CinemaState, seat_id: str, schedule_id: str = SID) -> str:
    return dict(state.snapshot(schedule_id))[seat_id]


# -- Booking ----------------------------------------------------------------


def test_booking_pertama_berhasil():
    service, counting, state, _ = _build()

    hasil = service.PesanKursi(_pesan("req-1", ["A1", "A2"]), FakeContext())

    assert hasil.success is True
    assert hasil.reservasi.status == cinema_pb2.RESERVASI_AKTIF
    assert counting.reserve_calls == 1
    assert _status(state, "A1") == "RESERVED"


def test_retry_booking_identik_tidak_mengulang_mutasi():
    service, counting, _, _ = _build()
    request = _pesan("req-1", ["A2", "A1"])

    pertama = service.PesanKursi(request, FakeContext())
    kedua = service.PesanKursi(request, FakeContext())

    assert pertama.success and kedua.success
    assert pertama.reservasi.reservation_id == kedua.reservasi.reservation_id
    assert counting.reserve_calls == 1


def test_retry_identik_dengan_urutan_kursi_berbeda_tetap_cache_hit():
    service, counting, _, _ = _build()

    pertama = service.PesanKursi(_pesan("req-1", ["A1", "A2"]), FakeContext())
    kedua = service.PesanKursi(_pesan("req-1", ["A2", "A1"]), FakeContext())

    assert kedua.reservasi.reservation_id == pertama.reservasi.reservation_id
    assert counting.reserve_calls == 1


def test_request_id_sama_seat_berbeda_ditolak():
    service, counting, state, _ = _build()
    service.PesanKursi(_pesan("req-1", ["A1"]), FakeContext())

    with pytest.raises(AbortError) as excinfo:
        service.PesanKursi(_pesan("req-1", ["A2"]), FakeContext())

    assert excinfo.value.code == grpc.StatusCode.FAILED_PRECONDITION
    assert counting.reserve_calls == 1
    assert _status(state, "A2") == "AVAILABLE"


def test_request_id_sama_schedule_berbeda_ditolak():
    service, counting, _, _ = _build()
    service.PesanKursi(_pesan("req-1", ["A1"], schedule_id=SID), FakeContext())

    with pytest.raises(AbortError) as excinfo:
        service.PesanKursi(_pesan("req-1", ["A1"], schedule_id=SID2), FakeContext())

    assert excinfo.value.code == grpc.StatusCode.FAILED_PRECONDITION
    assert counting.reserve_calls == 1


def test_konflik_kursi_tidak_menyebabkan_failure_poisoning():
    service, counting, state, _ = _build()

    holder = service.PesanKursi(_pesan("hold-1", ["A1"]), FakeContext())
    assert holder.success is True

    gagal = service.PesanKursi(_pesan("req-1", ["A1", "A2"]), FakeContext())
    assert gagal.success is False
    # All-or-nothing: A2 tidak ikut terkunci saat A1 konflik.
    assert _status(state, "A2") == "AVAILABLE"

    service.BatalkanPesanan(
        _batal("cancel-hold", holder.reservasi.reservation_id), FakeContext()
    )

    # Payload dan request_id sama, kondisi sudah berubah -> harus bisa sukses.
    ulang = service.PesanKursi(_pesan("req-1", ["A1", "A2"]), FakeContext())
    assert ulang.success is True
    assert counting.reserve_calls == 3  # hold + percobaan gagal + retry sukses


def test_retry_booking_setelah_dibatalkan_mengembalikan_snapshot_awal():
    service, counting, state, _ = _build()
    request = _pesan("req-1", ["A1", "A2"])

    pertama = service.PesanKursi(request, FakeContext())
    reservation_id = pertama.reservasi.reservation_id
    service.BatalkanPesanan(_batal("cancel-1", reservation_id), FakeContext())

    ulang = service.PesanKursi(request, FakeContext())

    # Snapshot hasil awal tetap AKTIF walau record asli sudah DIBATALKAN.
    assert ulang.reservasi.status == cinema_pb2.RESERVASI_AKTIF
    assert ulang.reservasi.reservation_id == reservation_id
    assert state.get_reservation(reservation_id).status == "CANCELLED"
    assert counting.reserve_calls == 1


def test_request_id_terlalu_panjang_ditolak():
    service, _, _, _ = _build()

    with pytest.raises(AbortError) as excinfo:
        service.PesanKursi(_pesan("x" * 129, ["A1"]), FakeContext())

    assert excinfo.value.code == grpc.StatusCode.INVALID_ARGUMENT


def test_request_id_kosong_tetap_ditolak():
    service, _, _, _ = _build()

    with pytest.raises(AbortError) as excinfo:
        service.PesanKursi(_pesan("", ["A1"]), FakeContext())

    assert excinfo.value.code == grpc.StatusCode.INVALID_ARGUMENT


# -- Pembatalan -------------------------------------------------------------


def test_pembatalan_pertama_berhasil():
    service, counting, state, _ = _build()
    booking = service.PesanKursi(_pesan("book-1", ["A1"]), FakeContext())

    hasil = service.BatalkanPesanan(
        _batal("cancel-1", booking.reservasi.reservation_id), FakeContext()
    )

    assert hasil.success is True
    assert hasil.reservasi.status == cinema_pb2.RESERVASI_DIBATALKAN
    assert counting.cancel_calls == 1
    assert _status(state, "A1") == "AVAILABLE"


def test_retry_pembatalan_identik_tidak_mengulang_mutasi():
    service, counting, _, _ = _build()
    booking = service.PesanKursi(_pesan("book-1", ["A1"]), FakeContext())
    request = _batal("cancel-1", booking.reservasi.reservation_id)

    pertama = service.BatalkanPesanan(request, FakeContext())
    kedua = service.BatalkanPesanan(request, FakeContext())

    assert pertama.reservasi.status == kedua.reservasi.status
    assert counting.cancel_calls == 1


def test_request_id_sama_reservation_berbeda_ditolak():
    service, counting, state, _ = _build()
    satu = service.PesanKursi(_pesan("book-1", ["A1"]), FakeContext())
    dua = service.PesanKursi(_pesan("book-2", ["A2"]), FakeContext())

    service.BatalkanPesanan(_batal("cancel-1", satu.reservasi.reservation_id), FakeContext())

    with pytest.raises(AbortError) as excinfo:
        service.BatalkanPesanan(_batal("cancel-1", dua.reservasi.reservation_id), FakeContext())

    assert excinfo.value.code == grpc.StatusCode.FAILED_PRECONDITION
    assert counting.cancel_calls == 1
    # Reservasi kedua tidak ikut dibatalkan.
    assert state.get_reservation(dua.reservasi.reservation_id).status == "ACTIVE"
    assert _status(state, "A2") == "RESERVED"


def test_pembatalan_tidak_ditemukan_tidak_memberi_cache_sukses_palsu():
    service, _, _, store = _build()

    with pytest.raises(AbortError) as excinfo:
        service.BatalkanPesanan(_batal("req-1", "tidak-ada"), FakeContext())
    assert excinfo.value.code == grpc.StatusCode.NOT_FOUND
    assert len(store) == 0

    booking = service.PesanKursi(_pesan("book-1", ["A1"]), FakeContext())
    hasil = service.BatalkanPesanan(
        _batal("req-1", booking.reservasi.reservation_id), FakeContext()
    )

    assert hasil.success is True
    assert hasil.reservasi.reservation_id == booking.reservasi.reservation_id
