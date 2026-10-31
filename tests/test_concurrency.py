"""Uji concurrency: race kursi sama, lintas jadwal independen, multi-kursi atomik."""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from stubs import cinema_pb2


def _schedules(client):
    return list(client.lihat_daftar_jadwal().daftar_jadwal)


def _available_seats(client, schedule_id: str, limit: int = 2) -> list[str]:
    daftar = client.lihat_daftar_kursi(schedule_id)
    return [k.id for k in daftar.daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE][:limit]


def _seat_status(client, schedule_id: str, seat_id: str) -> str:
    daftar = client.lihat_daftar_kursi(schedule_id)
    return cinema_pb2.StatusKursi.Name(next(k for k in daftar.daftar_kursi if k.id == seat_id).status)


def test_lomba_pesan_kursi_sama_tepat_satu_pemenang(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    seat = _available_seats(client, schedule_id, 1)[0]

    with ThreadPoolExecutor(max_workers=16) as pool:
        results = list(
            pool.map(
                lambda _: client.pesan_kursi(str(uuid.uuid4()), schedule_id, [seat]),
                range(16),
            )
        )

    berhasil = [r for r in results if r.success]
    gagal = [r for r in results if not r.success]

    assert len(berhasil) == 1
    assert len(gagal) == 15
    for r in gagal:
        assert "sudah dipesan" in r.message
    assert list(berhasil[0].reservasi.seat_ids) == [seat]
    assert _seat_status(client, schedule_id, seat) == "KURSI_RESERVED"


def test_request_id_concurrent_diproses_sekali(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    seats = _available_seats(client, schedule_id, 2)
    request_id = str(uuid.uuid4())

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: client.pesan_kursi(request_id, schedule_id, seats), range(8))
        )

    reservation_ids = {r.reservasi.reservation_id for r in results if r.HasField("reservasi")}

    assert all(r.success for r in results)
    assert len(reservation_ids) == 1
    assert set(seats) == set(results[0].reservasi.seat_ids)


def test_race_lintas_jadwal_independen(server):
    """Kursi sama di dua jadwal berbeda: keduanya harus sukses."""
    client = server.client
    s1, s2 = _schedules(client)[0].schedule_id, _schedules(client)[1].schedule_id

    s1_bebas = {k.id for k in client.lihat_daftar_kursi(s1).daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE}
    s2_bebas = {k.id for k in client.lihat_daftar_kursi(s2).daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE}
    kursi = sorted(s1_bebas & s2_bebas)[0]

    barrier = threading.Barrier(2)

    def attempt(schedule_id: str):
        barrier.wait()
        return client.pesan_kursi(str(uuid.uuid4()), schedule_id, [kursi])

    with ThreadPoolExecutor(max_workers=2) as pool:
        future1 = pool.submit(attempt, s1)
        future2 = pool.submit(attempt, s2)

    hasil1 = future1.result()
    hasil2 = future2.result()

    assert hasil1.success is True
    assert hasil2.success is True
    assert hasil1.reservasi.reservation_id != hasil2.reservasi.reservation_id


def test_overlap_kursi_all_or_nothing(server):
    """Pesan [X,Y] vs [Y,Z] bersamaan: tepat satu sukses tanpa partial booking."""
    client = server.client
    bebas: list[tuple[str, str]] = []  # (schedule_id, seat_id) dari jadwal vs jadwal pertama
    for jadwal in _schedules(client):
        daftar = [
            k.id
            for k in client.lihat_daftar_kursi(jadwal.schedule_id).daftar_kursi
            if k.status == cinema_pb2.KURSI_AVAILABLE
        ]
        if len(daftar) >= 3:
            bebas = [(jadwal.schedule_id, seat) for seat in sorted(daftar)]
            break
    schedule_id, (x, y, z) = bebas[0][0], (bebas[0][1], bebas[1][1], bebas[2][1])
    barrier = threading.Barrier(2)

    def attempt(seats: list[str]):
        barrier.wait()
        return client.pesan_kursi(str(uuid.uuid4()), schedule_id, seats)

    with ThreadPoolExecutor(max_workers=2) as pool:
        future1 = pool.submit(attempt, [x, y])
        future2 = pool.submit(attempt, [y, z])

    results = [future1.result(), future2.result()]
    berhas = [r for r in results if r.success]

    assert len(berhas) == 1

    def status(seat_id: str) -> str:
        return _seat_status(client, schedule_id, seat_id)

    # Y dimiliki tepat satu reservasi (pemenang).
    assert status(y) == "KURSI_RESERVED"
    # Kursi eksklusif pihak yang kalah TIDAK boleh ikut terkunci (no partial).
    if list(berhas[0].reservasi.seat_ids) == [x, y]:
        assert status(x) == "KURSI_RESERVED"
        assert status(z) == "KURSI_AVAILABLE"
    else:
        assert status(z) == "KURSI_RESERVED"
        assert status(x) == "KURSI_AVAILABLE"


def test_batal_concurrent_dengan_request_id_sama(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    seats = _available_seats(client, schedule_id, 2)
    hasil = client.pesan_kursi(str(uuid.uuid4()), schedule_id, seats)
    reservation_id = hasil.reservasi.reservation_id
    request_id = str(uuid.uuid4())

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(
            pool.map(lambda _: client.batalkan_pesanan(request_id, reservation_id), range(8))
        )

    assert all(r.success for r in results)
    for r in results:
        assert r.reservasi.reservation_id == reservation_id
        assert r.reservasi.status == cinema_pb2.RESERVASI_DIBATALKAN

    for seat_id in seats:
        assert _seat_status(client, schedule_id, seat_id) == "KURSI_AVAILABLE"
