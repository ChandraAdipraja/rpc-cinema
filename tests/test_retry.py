"""Uji retry & idempotency: hasil request_id yang sama dikembalikan ulang."""

from __future__ import annotations

import uuid

import grpc
import pytest

from cinema_client import CinemaRpcClient
from stubs import cinema_pb2


def _schedules(client):
    return list(client.lihat_daftar_jadwal().daftar_jadwal)


def _available_seats(client, schedule_id: str, limit: int = 2) -> list[str]:
    daftar = client.lihat_daftar_kursi(schedule_id)
    return [k.id for k in daftar.daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE][:limit]


def test_retry_pesan_dengan_request_id_sama(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    seats = _available_seats(client, schedule_id, 2)
    request_id = str(uuid.uuid4())

    pertama = client.pesan_kursi(request_id, schedule_id, seats)
    kedua = client.pesan_kursi(request_id, schedule_id, seats)
    ketiga = client.pesan_kursi(request_id, schedule_id, seats)

    assert pertama.success and kedua.success and ketiga.success
    ids = {
        pertama.reservasi.reservation_id,
        kedua.reservasi.reservation_id,
        ketiga.reservasi.reservation_id,
    }
    assert len(ids) == 1


def test_hasil_gagal_all_or_nothing_tersimpan_untuk_request_id_sama(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    seats = _available_seats(client, schedule_id, 2)
    # Kursi kedua dipesan dulu -> "taken".
    assert client.pesan_kursi(str(uuid.uuid4()), schedule_id, [seats[1]]).success is True

    request_id = str(uuid.uuid4())
    pertama = client.pesan_kursi(request_id, schedule_id, seats)
    assert pertama.success is False

    kedua = client.pesan_kursi(request_id, schedule_id, seats)
    assert kedua.success == pertama.success
    assert kedua.message == pertama.message
    assert kedua.HasField("reservasi") == pertama.HasField("reservasi")

    # Tidak partial: kursi pertama tetap bebas.
    daftar = client.lihat_daftar_kursi(schedule_id)
    kursi = next(k for k in daftar.daftar_kursi if k.id == seats[0])
    assert kursi.status == cinema_pb2.KURSI_AVAILABLE


def test_retry_batal_dengan_request_id_sama(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    seats = _available_seats(client, schedule_id, 2)
    hasil = client.pesan_kursi(str(uuid.uuid4()), schedule_id, seats)
    request_id = str(uuid.uuid4())

    pertama = client.batalkan_pesanan(request_id, hasil.reservasi.reservation_id)
    kedua = client.batalkan_pesanan(request_id, hasil.reservasi.reservation_id)

    assert pertama.success is True
    assert kedua.message == pertama.message
    assert kedua.reservasi.status == pertama.reservasi.status
    assert list(kedua.reservasi.seat_ids) == list(pertama.reservasi.seat_ids)


def test_target_tidak_ada_akan_gagal_setelah_retries():
    # UNAVAILABLE retryable; setelah percobaan habis client harus tetap gagal.
    client = CinemaRpcClient(
        target="localhost:1",  # port hampir pasti tidak ada listener
        timeout=1.0,
        max_retries=1,
        backoff_base=0.05,
    )
    try:
        with pytest.raises(grpc.RpcError) as excinfo:
            client.lihat_daftar_jadwal()
        assert excinfo.value.code() in (
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
        )
    finally:
        client.close()
