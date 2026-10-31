"""Test end-to-end idempotency lewat gRPC server sungguhan (subprocess)."""

from __future__ import annotations

import uuid

import grpc
import pytest

from stubs import cinema_pb2


def _schedules(client):
    return list(client.lihat_daftar_jadwal().daftar_jadwal)


def _free_seats(client, schedule_id: str) -> list[str]:
    daftar = client.lihat_daftar_kursi(schedule_id)
    return [k.id for k in daftar.daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE]


def _pick(client, count: int) -> tuple[str, list[str]]:
    """Pilih jadwal pertama yang punya cukup kursi bebas."""
    for jadwal in _schedules(client):
        bebas = _free_seats(client, jadwal.schedule_id)
        if len(bebas) >= count:
            return jadwal.schedule_id, bebas[:count]
    raise AssertionError("tidak ada jadwal dengan kursi bebas yang cukup")


def _status(client, schedule_id: str, seat_id: str) -> str:
    daftar = client.lihat_daftar_kursi(schedule_id)
    kursi = next(k for k in daftar.daftar_kursi if k.id == seat_id)
    return cinema_pb2.StatusKursi.Name(kursi.status)


def _cancel(client, reservation_id: str) -> None:
    client.batalkan_pesanan(str(uuid.uuid4()), reservation_id)


def test_retry_booking_identik_mengembalikan_reservasi_sama(server):
    client = server.client
    schedule_id, seats = _pick(client, 2)
    request_id = str(uuid.uuid4())

    pertama = client.pesan_kursi(request_id, schedule_id, seats)
    kedua = client.pesan_kursi(request_id, schedule_id, seats)

    assert pertama.success and kedua.success
    assert pertama.reservasi.reservation_id == kedua.reservasi.reservation_id
    assert set(kedua.reservasi.seat_ids) == set(seats)
    _cancel(client, pertama.reservasi.reservation_id)


def test_request_id_sama_seat_berbeda_ditolak(server):
    client = server.client
    schedule_id, seats = _pick(client, 2)
    request_id = str(uuid.uuid4())

    pertama = client.pesan_kursi(request_id, schedule_id, [seats[0]])
    assert pertama.success is True

    with pytest.raises(grpc.RpcError) as excinfo:
        client.pesan_kursi(request_id, schedule_id, [seats[1]])
    assert excinfo.value.code() == grpc.StatusCode.FAILED_PRECONDITION
    assert _status(client, schedule_id, seats[1]) == "KURSI_AVAILABLE"

    _cancel(client, pertama.reservasi.reservation_id)


def test_request_id_sama_schedule_berbeda_ditolak(server):
    client = server.client
    schedules = _schedules(client)
    s1, s2 = schedules[0].schedule_id, schedules[1].schedule_id
    seat_s1 = _free_seats(client, s1)[0]
    seat_s2 = _free_seats(client, s2)[0]
    request_id = str(uuid.uuid4())

    pertama = client.pesan_kursi(request_id, s1, [seat_s1])
    assert pertama.success is True

    with pytest.raises(grpc.RpcError) as excinfo:
        client.pesan_kursi(request_id, s2, [seat_s2])
    assert excinfo.value.code() == grpc.StatusCode.FAILED_PRECONDITION
    assert _status(client, s2, seat_s2) == "KURSI_AVAILABLE"

    _cancel(client, pertama.reservasi.reservation_id)


def test_retry_pembatalan_identik(server):
    client = server.client
    schedule_id, seats = _pick(client, 1)
    booking = client.pesan_kursi(str(uuid.uuid4()), schedule_id, seats)
    request_id = str(uuid.uuid4())

    pertama = client.batalkan_pesanan(request_id, booking.reservasi.reservation_id)
    kedua = client.batalkan_pesanan(request_id, booking.reservasi.reservation_id)

    assert pertama.success and kedua.success
    assert pertama.reservasi.reservation_id == kedua.reservasi.reservation_id
    assert kedua.reservasi.status == cinema_pb2.RESERVASI_DIBATALKAN
    assert _status(client, schedule_id, seats[0]) == "KURSI_AVAILABLE"


def test_konflik_kursi_tidak_poisoned_end_to_end(server):
    client = server.client
    schedule_id, seats = _pick(client, 2)
    holder = client.pesan_kursi(str(uuid.uuid4()), schedule_id, [seats[0]])
    assert holder.success is True

    request_id = str(uuid.uuid4())
    gagal = client.pesan_kursi(request_id, schedule_id, seats)
    assert gagal.success is False
    assert _status(client, schedule_id, seats[1]) == "KURSI_AVAILABLE"

    _cancel(client, holder.reservasi.reservation_id)

    ulang = client.pesan_kursi(request_id, schedule_id, seats)
    assert ulang.success is True
    _cancel(client, ulang.reservasi.reservation_id)


def test_retry_booking_setelah_dibatalkan_tetap_snapshot_awal(server):
    client = server.client
    schedule_id, seats = _pick(client, 2)
    request_id = str(uuid.uuid4())

    pertama = client.pesan_kursi(request_id, schedule_id, seats)
    reservation_id = pertama.reservasi.reservation_id
    _cancel(client, reservation_id)

    ulang = client.pesan_kursi(request_id, schedule_id, seats)

    assert ulang.success is True
    assert ulang.reservasi.reservation_id == reservation_id
    assert ulang.reservasi.status == cinema_pb2.RESERVASI_AKTIF
    detail = client.lihat_detail_pesanan(reservation_id)
    assert detail.reservasi.status == cinema_pb2.RESERVASI_DIBATALKAN
