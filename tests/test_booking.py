"""Uji fungsional alur reservasi: jadwal, multi-kursi, independensi lintas jadwal."""

from __future__ import annotations

import uuid

import grpc
import pytest

from stubs import cinema_pb2


def _schedules(client):
    return list(client.lihat_daftar_jadwal().daftar_jadwal)


def _seat_status(client, schedule_id: str, seat_id: str) -> str:
    daftar = client.lihat_daftar_kursi(schedule_id)
    kursi = next(k for k in daftar.daftar_kursi if k.id == seat_id)
    return cinema_pb2.StatusKursi.Name(kursi.status)


def test_daftar_jadwal_dari_server(server):
    client = server.client
    jadwal_list = _schedules(client)

    assert len(jadwal_list) >= 12  # 4 film x 3 jam
    pertama = jadwal_list[0]
    assert pertama.schedule_id
    assert pertama.judul
    assert pertama.jam_tayang
    # Judul film dengan jam berbeda muncul berulang, schedule_id-nya unik.
    ids = {j.schedule_id for j in jadwal_list}
    assert len(ids) == len(jadwal_list)


def test_pesan_multi_kursi_sukses(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    daftar = client.lihat_daftar_kursi(schedule_id)
    seats = [k.id for k in daftar.daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE][:2]

    hasil = client.pesan_kursi(str(uuid.uuid4()), schedule_id, seats)

    assert hasil.success is True
    assert set(hasil.reservasi.seat_ids) == set(seats)
    assert hasil.reservasi.schedule_id == schedule_id
    assert hasil.reservasi.status == cinema_pb2.RESERVASI_AKTIF
    for seat_id in seats:
        assert _seat_status(client, schedule_id, seat_id) == "KURSI_RESERVED"


def test_multi_kursi_all_or_nothing_ketika_ada_kursi_taken(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id

    # Ambil dua kursi bebas: satu dipesan dulu (jadi taken), satu disimpan.
    daftar = client.lihat_daftar_kursi(schedule_id)
    seats_bebas = [k.id for k in daftar.daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE]
    kursi_bebas, kursi_yang_diparkir = seats_bebas[0], seats_bebas[1]
    assert client.pesan_kursi(str(uuid.uuid4()), schedule_id, [kursi_yang_diparkir]).success is True

    # Coba pesan kursi taken + kursi bebas -> HARUS seluruhnya gagal.
    hasil = client.pesan_kursi(
        str(uuid.uuid4()), schedule_id, [kursi_bebas, kursi_yang_diparkir]
    )

    assert hasil.success is False
    assert "sudah dipesan" in hasil.message
    # Tidak boleh partial booking: kursi bebas tetap bebas.
    assert _seat_status(client, schedule_id, kursi_bebas) == "KURSI_AVAILABLE"


def test_independensi_lintas_jadwal(server):
    """Kursi yang dipesan di jadwal X tidak memengaruhi kursi sama di jadwal lain."""
    client = server.client
    schedules = _schedules(client)
    s1, s2 = schedules[0].schedule_id, schedules[1].schedule_id

    # Pilih kursi yang bebas di KEDUA jadwal (server shared antar test).
    s1_bebas = {k.id for k in client.lihat_daftar_kursi(s1).daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE}
    s2_bebas = {k.id for k in client.lihat_daftar_kursi(s2).daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE}
    kursi = sorted(s1_bebas & s2_bebas)[0]

    hasil = client.pesan_kursi(str(uuid.uuid4()), s1, [kursi])
    assert hasil.success is True

    assert _seat_status(client, s1, kursi) == "KURSI_RESERVED"
    assert _seat_status(client, s2, kursi) == "KURSI_AVAILABLE"

    # Dan kursi itu di jadwal lain masih bisa dipesan orang lain.
    hasil2 = client.pesan_kursi(str(uuid.uuid4()), s2, [kursi])
    assert hasil2.success is True


def test_batal_membebaskan_semua_kursi(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    daftar = client.lihat_daftar_kursi(schedule_id)
    seats = [k.id for k in daftar.daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE][:2]

    hasil = client.pesan_kursi(str(uuid.uuid4()), schedule_id, seats)
    reservation_id = hasil.reservasi.reservation_id

    batal = client.batalkan_pesanan(str(uuid.uuid4()), reservation_id)
    assert batal.success is True
    assert batal.reservasi.status == cinema_pb2.RESERVASI_DIBATALKAN

    detail = client.lihat_detail_pesanan(reservation_id)
    assert detail.reservasi.status == cinema_pb2.RESERVASI_DIBATALKAN
    for seat_id in seats:
        assert _seat_status(client, schedule_id, seat_id) == "KURSI_AVAILABLE"


def test_detail_pesanan(server):
    client = server.client
    schedule_id = _schedules(client)[0].schedule_id
    daftar = client.lihat_daftar_kursi(schedule_id)
    seats = [k.id for k in daftar.daftar_kursi if k.status == cinema_pb2.KURSI_AVAILABLE][:2]

    hasil = client.pesan_kursi(str(uuid.uuid4()), schedule_id, seats)
    detail = client.lihat_detail_pesanan(hasil.reservasi.reservation_id)

    assert detail.found is True
    assert detail.reservasi.schedule_id == schedule_id
    assert set(detail.reservasi.seat_ids) == set(seats)


def test_pesan_jadwal_tidak_dikenal(server):
    with pytest.raises(grpc.RpcError) as excinfo:
        server.client.pesan_kursi(str(uuid.uuid4()), "jadwal-hantu", ["A1"])
    assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


def test_pesan_kursi_tidak_ada_di_jadwal_invalid_argument(server):
    schedule_id = _schedules(server.client)[0].schedule_id
    with pytest.raises(grpc.RpcError) as excinfo:
        server.client.pesan_kursi(str(uuid.uuid4()), schedule_id, ["ZZ9"])
    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_pesan_multi_kursi_ganda_invalid_argument(server):
    schedule_id = _schedules(server.client)[0].schedule_id
    with pytest.raises(grpc.RpcError) as excinfo:
        server.client.pesan_kursi(str(uuid.uuid4()), schedule_id, ["A1", "A1"])
    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_pesan_tanpa_venue_dan_kursi_invalid_argument(server):
    schedule_id = _schedules(server.client)[0].schedule_id
    with pytest.raises(grpc.RpcError) as excinfo:
        server.client.pesan_kursi("", schedule_id, ["A1"])
    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT

    with pytest.raises(grpc.RpcError) as excinfo:
        server.client.pesan_kursi(str(uuid.uuid4()), schedule_id, [])
    assert excinfo.value.code() == grpc.StatusCode.INVALID_ARGUMENT


def test_lihat_kursi_jadwal_tidak_dikenal(server):
    with pytest.raises(grpc.RpcError) as excinfo:
        server.client.lihat_daftar_kursi("jadwal-hantu")
    assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


def test_detail_reservasi_tidak_ditemukan(server):
    with pytest.raises(grpc.RpcError) as excinfo:
        server.client.lihat_detail_pesanan("tidak-ada")
    assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND


def test_batal_reservasi_tidak_ditemukan(server):
    with pytest.raises(grpc.RpcError) as excinfo:
        server.client.batalkan_pesanan(str(uuid.uuid4()), "tidak-ada")
    assert excinfo.value.code() == grpc.StatusCode.NOT_FOUND
