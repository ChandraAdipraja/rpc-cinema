"""Uji end-to-end FastAPI Gateway: HTTP -> gRPC -> HTTP, termasuk SSE per jadwal."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
import pytest

ROOT = Path(__file__).resolve().parents[1]


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class GatewayHandle:
    port: int
    url: str


def _jadwal_list(base_url: str) -> list[dict]:
    response = httpx.get(f"{base_url}/api/jadwal", timeout=10)
    response.raise_for_status()
    return response.json()


def _first_two_schedules(base_url: str) -> tuple[str, str]:
    jadwal_list = _jadwal_list(base_url)
    return jadwal_list[0]["schedule_id"], jadwal_list[1]["schedule_id"]


def _available_seats(base_url: str, schedule_id: str, limit: int = 2) -> list[str]:
    kursi_list = httpx.get(
        f"{base_url}/api/kursi",
        params={"schedule_id": schedule_id},
        timeout=10,
    ).raise_for_status().json()
    return [k["id"] for k in kursi_list if k["status"] == "AVAILABLE"][:limit]


@pytest.fixture()
def gateway(server):
    port = _free_port()
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "gateway.app.main:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ROOT),
        env={**os.environ, "GRPC_TARGET": f"localhost:{server.port}"},
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    base_url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 20.0
    ready = False
    while time.time() < deadline:
        try:
            response = httpx.get(f"{base_url}/api/health", timeout=2.0)
            if response.status_code == 200:
                ready = True
                break
        except httpx.HTTPError:
            pass
        time.sleep(0.3)

    if not ready:
        process.terminate()
        pytest.fail("Gateway tidak siap dalam batas waktu")

    handle = GatewayHandle(port=port, url=base_url)
    yield handle
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def test_health(gateway):
    response = httpx.get(f"{gateway.url}/api/health", timeout=5)
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_daftar_jadwal_via_gateway(gateway):
    jadwal_list = _jadwal_list(gateway.url)
    assert len(jadwal_list) >= 12
    for jadwal in jadwal_list:
        assert set(jadwal) == {"schedule_id", "judul", "genre", "durasi_menit", "jam_tayang"}


def test_daftar_kursi_via_gateway(gateway):
    schedule_id, _ = _first_two_schedules(gateway.url)
    response = httpx.get(
        f"{gateway.url}/api/kursi",
        params={"schedule_id": schedule_id},
        timeout=10,
    )
    assert response.status_code == 200
    kursi_list = response.json()
    assert len(kursi_list) >= 6
    assert all(set(k) == {"id", "status"} for k in kursi_list)


def test_pesan_multi_kursi_detail_batal_via_gateway(gateway):
    base = gateway.url
    schedule_id, _ = _first_two_schedules(gateway.url)
    seats = _available_seats(base, schedule_id, 2)

    hasil = httpx.post(
        f"{base}/api/pesan",
        json={"schedule_id": schedule_id, "seat_ids": seats},
        timeout=10,
    )
    assert hasil.status_code == 200
    body = hasil.json()
    assert body["success"] is True
    reservation = body["reservasi"]
    assert set(reservation["seat_ids"]) == set(seats)
    assert reservation["schedule_id"] == schedule_id
    assert reservation["status"] == "AKTIF"

    detail = httpx.get(f"{base}/api/pesanan/{reservation['reservation_id']}", timeout=10)
    assert detail.status_code == 200
    assert set(detail.json()["seat_ids"]) == set(seats)

    batal = httpx.post(
        f"{base}/api/batal",
        json={"reservation_id": reservation["reservation_id"]},
        timeout=10,
    )
    assert batal.status_code == 200
    assert batal.json()["reservasi"]["status"] == "DIBATALKAN"


def test_pesan_kursi_terparkir_menghasilkan_409(gateway):
    base = gateway.url
    schedule_id = _first_two_schedules(base)[0]
    seats = _available_seats(base, schedule_id, 2)
    assert (
        httpx.post(
            f"{base}/api/pesan",
            json={"schedule_id": schedule_id, "seat_ids": [seats[0]]},
            timeout=10,
        ).status_code
        == 200
    )

    konflik = httpx.post(
        f"{base}/api/pesan",
        json={"schedule_id": schedule_id, "seat_ids": seats},
        timeout=10,
    )
    assert konflik.status_code == 409
    assert "sudah dipesan" in konflik.json()["detail"]


def test_independensi_lintas_jadwal_via_gateway(gateway):
    base = gateway.url
    s1, s2 = _first_two_schedules(base)
    # Kursi yang bebas di KEDUA jadwal (server shared antar test).
    s1_bebas = {k["id"] for k in httpx.get(f"{base}/api/kursi", params={"schedule_id": s1}, timeout=10).json() if k["status"] == "AVAILABLE"}
    s2_bebas = {k["id"] for k in httpx.get(f"{base}/api/kursi", params={"schedule_id": s2}, timeout=10).json() if k["status"] == "AVAILABLE"}
    seat = sorted(s1_bebas & s2_bebas)[0]

    assert (
        httpx.post(
            f"{base}/api/pesan",
            json={"schedule_id": s1, "seat_ids": [seat]},
            timeout=10,
        ).status_code
        == 200
    )

    s1_kursi = httpx.get(f"{base}/api/kursi", params={"schedule_id": s1}, timeout=10).json()
    s2_kursi = httpx.get(f"{base}/api/kursi", params={"schedule_id": s2}, timeout=10).json()
    assert next(k for k in s1_kursi if k["id"] == seat)["status"] == "RESERVED"
    assert next(k for k in s2_kursi if k["id"] == seat)["status"] == "AVAILABLE"


def test_pesan_jadwal_tidak_dikenal_404(gateway):
    response = httpx.post(
        f"{gateway.url}/api/pesan",
        json={"schedule_id": "jadwal-hantu", "seat_ids": ["A1"]},
        timeout=10,
    )
    assert response.status_code == 404


def test_pesan_kursi_tidak_ada_400(gateway):
    schedule_id = _first_two_schedules(gateway.url)[0]
    response = httpx.post(
        f"{gateway.url}/api/pesan",
        json={"schedule_id": schedule_id, "seat_ids": ["ZZ9"]},
        timeout=10,
    )
    assert response.status_code == 400


def test_detail_unknown_404(gateway):
    response = httpx.get(f"{gateway.url}/api/pesanan/tidak-ada", timeout=10)
    assert response.status_code == 404


def test_sse_stream_kursi_per_jadwal(gateway, server):
    """SSE mengirim snapshot awal 6 kursi jadwal itu, lalu update RESERVED."""
    base = gateway.url
    schedule_id = _first_two_schedules(base)[0]
    seat = _available_seats(base, schedule_id, 1)[0]

    with httpx.stream(
        "GET",
        f"{base}/api/stream/kursi",
        params={"schedule_id": schedule_id},
        timeout=20.0,
    ) as response:
        assert response.status_code == 200
        lines = response.iter_lines()

        def next_data():
            for line in lines:
                if line.startswith("data: "):
                    return json.loads(line[len("data: "):])
            return None

        received: Optional[dict] = None
        kursi_awal: dict[str, str] = {}
        while len(kursi_awal) < 6:
            payload = next_data()
            assert payload is not None
            kursi = payload["kursi"]
            kursi_awal[kursi["id"]] = kursi["status"]
        del received
        assert kursi_awal[seat] == "AVAILABLE"

        hasil = server.client.pesan_kursi(str(uuid.uuid4()), schedule_id, [seat])
        assert hasil.success is True

        deadline = time.time() + 15.0
        while time.time() < deadline:
            payload = next_data()
            assert payload is not None
            kursi = payload["kursi"]
            if kursi["id"] == seat and kursi["status"] == "RESERVED":
                break
        else:
            pytest.fail("Tidak menerima update RESERVED sebelum batas waktu")

        server.client.batalkan_pesanan(str(uuid.uuid4()), hasil.reservasi.reservation_id)


# -- Idempotency end-to-end lewat HTTP -------------------------------------


def _cancel_via_gateway(base: str, reservation_id: str) -> None:
    httpx.post(
        f"{base}/api/batal",
        json={"reservation_id": reservation_id},
        timeout=10,
    )


def test_pesan_request_id_sama_idempotent_via_gateway(gateway):
    """Key yang sama dari client harus diteruskan apa adanya ke gRPC."""
    base = gateway.url
    schedule_id = _first_two_schedules(base)[0]
    seat = _available_seats(base, schedule_id, 1)[0]
    body = {
        "schedule_id": schedule_id,
        "seat_ids": [seat],
        "request_id": uuid.uuid4().hex,
    }

    pertama = httpx.post(f"{base}/api/pesan", json=body, timeout=10)
    kedua = httpx.post(f"{base}/api/pesan", json=body, timeout=10)

    assert pertama.status_code == 200
    assert kedua.status_code == 200
    reservasi_pertama = pertama.json()["reservasi"]["reservation_id"]
    reservasi_kedua = kedua.json()["reservasi"]["reservation_id"]
    # Kalau gateway membuat UUID baru, panggilan kedua akan 409 (kursi sudah
    # dipegang reservasi pertama) dan tidak mungkin mengembalikan ID sama.
    assert reservasi_pertama == reservasi_kedua

    _cancel_via_gateway(base, reservasi_pertama)


def test_pesan_request_id_sama_payload_berbeda_409(gateway):
    base = gateway.url
    schedule_id = _first_two_schedules(base)[0]
    seats = _available_seats(base, schedule_id, 2)
    request_id = uuid.uuid4().hex

    pertama = httpx.post(
        f"{base}/api/pesan",
        json={"schedule_id": schedule_id, "seat_ids": [seats[0]], "request_id": request_id},
        timeout=10,
    )
    assert pertama.status_code == 200

    kedua = httpx.post(
        f"{base}/api/pesan",
        json={"schedule_id": schedule_id, "seat_ids": [seats[1]], "request_id": request_id},
        timeout=10,
    )
    assert kedua.status_code == 409
    assert "payload berbeda" in kedua.json()["detail"]

    kursi = httpx.get(
        f"{base}/api/kursi", params={"schedule_id": schedule_id}, timeout=10
    ).json()
    assert next(k for k in kursi if k["id"] == seats[1])["status"] == "AVAILABLE"

    _cancel_via_gateway(base, pertama.json()["reservasi"]["reservation_id"])


def test_pesan_tanpa_request_id_tetap_kompatibel(gateway):
    base = gateway.url
    schedule_id = _first_two_schedules(base)[0]
    seat = _available_seats(base, schedule_id, 1)[0]

    hasil = httpx.post(
        f"{base}/api/pesan",
        json={"schedule_id": schedule_id, "seat_ids": [seat]},
        timeout=10,
    )

    assert hasil.status_code == 200
    assert hasil.json()["success"] is True
    _cancel_via_gateway(base, hasil.json()["reservasi"]["reservation_id"])


def test_batal_request_id_sama_dapat_di_retry(gateway):
    base = gateway.url
    schedule_id = _first_two_schedules(base)[0]
    seat = _available_seats(base, schedule_id, 1)[0]

    booking = httpx.post(
        f"{base}/api/pesan",
        json={"schedule_id": schedule_id, "seat_ids": [seat]},
        timeout=10,
    )
    reservation_id = booking.json()["reservasi"]["reservation_id"]
    request_id = uuid.uuid4().hex
    body = {"reservation_id": reservation_id, "request_id": request_id}

    pertama = httpx.post(f"{base}/api/batal", json=body, timeout=10)
    kedua = httpx.post(f"{base}/api/batal", json=body, timeout=10)

    assert pertama.status_code == 200
    assert kedua.status_code == 200
    assert pertama.json()["reservasi"]["reservation_id"] == reservation_id
    assert kedua.json()["reservasi"]["reservation_id"] == reservation_id
    assert kedua.json()["reservasi"]["status"] == "DIBATALKAN"


def test_request_id_terlalu_panjang_ditolak_gateway(gateway):
    base = gateway.url
    schedule_id = _first_two_schedules(base)[0]
    seat = _available_seats(base, schedule_id, 1)[0]

    hasil = httpx.post(
        f"{base}/api/pesan",
        json={"schedule_id": schedule_id, "seat_ids": [seat], "request_id": "x" * 129},
        timeout=10,
    )

    assert hasil.status_code == 422
