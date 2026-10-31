"""Composition root gRPC Server Cinema.

Menyusun state (multi-jadwal), idempotency, lock, lalu menjalankan service
di port GRPC_PORT (default 50051).
Jalankan: .venv/Scripts/python.exe grpc_server/server.py
"""

from __future__ import annotations

import os
import sys
from concurrent import futures
from pathlib import Path

import grpc

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from core.idempotency import IdempotencyStore
from core.locking import StateLock
from core.storage import CinemaState, Schedule
from services.cinema_service import CinemaService
from stubs import cinema_pb2_grpc

GRPC_PORT = os.getenv("GRPC_PORT", "50051")

DEFAULT_SEAT_IDS = ("A1", "A2", "A3", "B1", "B2", "B3")

# Worker ditambah karena handler streaming bertahan lama selama subscriber aktif.
MAX_WORKERS = 32

# Katalog film & jadwal: source of truth di server (frontend mengambil via RPC).
_FILM_CATALOG = [
    {"film_id": "m-gerhana", "judul": "Gerhana Sunyi", "genre": "Drama Misteri", "durasi_menit": 108, "jadwal": ["10:30", "13:45", "19:00"]},
    {"film_id": "m-orbit", "judul": "Orbit Terakhir", "genre": "Sci-Fi Petualangan", "durasi_menit": 124, "jadwal": ["11:15", "16:00", "21:15"]},
    {"film_id": "m-senja", "judul": "Kopi Pagi di Senja", "genre": "Romansa", "durasi_menit": 96, "jadwal": ["09:45", "14:30", "18:20"]},
    {"film_id": "m-lumbung", "judul": "Lumbung Rahasia", "genre": "Animasi Keluarga", "durasi_menit": 89, "jadwal": ["10:00", "12:45", "17:30"]},
]


def build_schedules() -> list[Schedule]:
    schedules = []
    for film in _FILM_CATALOG:
        for jam in film["jadwal"]:
            schedules.append(
                Schedule(
                    schedule_id=f"{film['film_id']}-{jam.replace(':', '')}",
                    judul=film["judul"],
                    genre=film["genre"],
                    durasi_menit=film["durasi_menit"],
                    jam_tayang=jam,
                )
            )
    return schedules


def build_service() -> CinemaService:
    state_lock = StateLock()
    state = CinemaState(
        lock=state_lock.rlock,
        schedules=build_schedules(),
        seat_ids=DEFAULT_SEAT_IDS,
    )
    idempotency = IdempotencyStore()
    return CinemaService(state=state, idempotency=idempotency, state_lock=state_lock)


def serve() -> None:
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=MAX_WORKERS))
    cinema_pb2_grpc.add_CinemaServiceServicer_to_server(build_service(), server)
    server.add_insecure_port(f"[::]:{GRPC_PORT}")
    server.start()
    print(f"[server] Cinema gRPC Server berjalan di port {GRPC_PORT} "
          f"({len(build_schedules())} jadwal aktif, Ctrl+C untuk berhenti)")
    server.wait_for_termination()


if __name__ == "__main__":
    serve()
