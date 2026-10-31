"""Uji server streaming StreamStatusKursi per jadwal + isolasi antar jadwal."""

from __future__ import annotations

import queue
import threading
import time
import uuid

import grpc
import pytest

from stubs import cinema_pb2

SEAT_COUNT = 6


def _schedules(client):
    return list(client.lihat_daftar_jadwal().daftar_jadwal)


def test_stream_satu_jadwal_snapshot_dan_update(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    updates: queue.Queue = queue.Queue()

    def reader() -> None:
        try:
            for update in client.stream_status_kursi(schedule_id):
                updates.put(update)
        except grpc.RpcError:
            pass

    threading.Thread(target=reader, daemon=True).start()

    snapshot = [updates.get(timeout=15) for _ in range(SEAT_COUNT)]
    statuses = {u.kursi.id: u.kursi.status for u in snapshot}
    assert len(statuses) == SEAT_COUNT
    assert cinema_pb2.KURSI_RESERVED not in statuses.values()

    seat = next(sid for sid, status in statuses.items() if status == cinema_pb2.KURSI_AVAILABLE)
    hasil = client.pesan_kursi(str(uuid.uuid4()), schedule_id, [seat])
    assert hasil.success is True
    _tunggu_status(updates, seat, cinema_pb2.KURSI_RESERVED)

    client.batalkan_pesanan(str(uuid.uuid4()), hasil.reservasi.reservation_id)
    _tunggu_status(updates, seat, cinema_pb2.KURSI_AVAILABLE)


def test_stream_terisolasi_antar_jadwal(server):
    """Mutasi jadwal lain TIDAK harus memicu update ke subscriber jadwal ini."""
    client = server.client
    s1, s2 = _schedules(client)[0].schedule_id, _schedules(client)[1].schedule_id

    updates: queue.Queue = queue.Queue()

    def reader() -> None:
        try:
            for update in client.stream_status_kursi(s1):
                updates.put(update)
        except grpc.RpcError:
            pass

    threading.Thread(target=reader, daemon=True).start()

    # Konsumsi snapshot awal jadwal s1 (6 kursi).
    received = [updates.get(timeout=15) for _ in range(SEAT_COUNT)]
    assert len({u.kursi.id for u in received}) == SEAT_COUNT

    # Pesan kursi di jadwal s2 — versi jadwal s1 tidak berubah.
    kursi_s2 = next(
        k.id
        for k in client.lihat_daftar_kursi(s2).daftar_kursi
        if k.status == cinema_pb2.KURSI_AVAILABLE
    )
    assert client.pesan_kursi(str(uuid.uuid4()), s2, [kursi_s2]).success is True

    # Dalam 3 detik TIDAK boleh ada update baru untuk subscriber s1.
    with pytest.raises(queue.Empty):
        updates.get(timeout=3.0)


def test_stream_batalkan_mengembalikan_available(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    updates: queue.Queue = queue.Queue()

    def reader() -> None:
        try:
            for update in client.stream_status_kursi(schedule_id):
                updates.put(update)
        except grpc.RpcError:
            pass

    threading.Thread(target=reader, daemon=True).start()
    [updates.get(timeout=15) for _ in range(SEAT_COUNT)]

    kursi = next(
        k.id
        for k in client.lihat_daftar_kursi(schedule_id).daftar_kursi
        if k.status == cinema_pb2.KURSI_AVAILABLE
    )
    hasil = client.pesan_kursi(str(uuid.uuid4()), schedule_id, [kursi])
    reservation_id = hasil.reservasi.reservation_id
    _tunggu_status(updates, kursi, cinema_pb2.KURSI_RESERVED)

    client.batalkan_pesanan(str(uuid.uuid4()), reservation_id)
    _tunggu_status(updates, kursi, cinema_pb2.KURSI_AVAILABLE)


def test_stream_jadwal_hantu_gagal(server):
    with pytest.raises(grpc.RpcError) as excinfo:
        for _update in server.client.stream_status_kursi("jadwal-hantu"):
            pass
    assert excinfo.value.code() in (
        grpc.StatusCode.NOT_FOUND,
        grpc.StatusCode.INVALID_ARGUMENT,
    )


def _tunggu_status(
    updates: queue.Queue,
    seat_id: str,
    target_status: int,
    timeout: float = 15.0,
) -> None:
    """Scan antrean update sampai kursi target punya status yang diharapkan."""
    deadline = time.time() + timeout
    while True:
        sisa = deadline - time.time()
        update = updates.get(timeout=max(0.05, sisa))
        if update.kursi.id == seat_id and update.kursi.status == target_status:
            return
