"""Client sederhana untuk menguji koneksi ke Cinema gRPC Server.

Memanggil LihatDaftarJadwal + LihatDaftarKursi dengan deadline (contoh timeout).
Jalankan server dulu:  .venv/Scripts/python.exe grpc_server/server.py
Lalu jalankan client:  .venv/Scripts/python.exe tests/test_connection.py
"""

import os
import sys
from pathlib import Path

import grpc

BASE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE_DIR.parent / "grpc_server" / "generated"))

import cinema_pb2
import cinema_pb2_grpc

TARGET = os.getenv("GRPC_TARGET", "localhost:50051")
TIMEOUT_SECONDS = 5.0


def main() -> int:
    try:
        with grpc.insecure_channel(TARGET) as channel:
            stub = cinema_pb2_grpc.CinemaServiceStub(channel)
            jadwal = stub.LihatDaftarJadwal(
                cinema_pb2.LihatDaftarJadwalRequest(),
                timeout=TIMEOUT_SECONDS,
            )
            schedule_id = jadwal.daftar_jadwal[0].schedule_id
            response = stub.LihatDaftarKursi(
                cinema_pb2.LihatDaftarKursiRequest(schedule_id=schedule_id),
                timeout=TIMEOUT_SECONDS,
            )
    except (grpc.RpcError, IndexError) as err:
        detail = getattr(err, "details", lambda: str(err))()
        print(f"[client] GAGAL: {detail}")
        return 1

    print(f"[client] Terhubung ke {TARGET}")
    print(f"[client] Jadwal: {schedule_id}")
    for kursi in response.daftar_kursi:
        status = cinema_pb2.StatusKursi.Name(kursi.status)
        print(f"[client] Kursi {kursi.id}: {status}")
    print(f"[client] OK — {len(response.daftar_kursi)} kursi diterima")
    return 0


if __name__ == "__main__":
    sys.exit(main())
