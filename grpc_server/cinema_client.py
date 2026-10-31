"""Client RPC Cinema dengan timeout dan retry (exponential backoff).

Dipakai oleh gateway (fase berikutnya), test suite, dan uji manual:
.venv/Scripts/python.exe grpc_server/cinema_client.py

Retry hanya dilakukan untuk operasi idempotent (punya request_id) dan
hanya pada error yang layak dicoba ulang (UNAVAILABLE / DEADLINE_EXCEEDED),
dengan jumlah percobaan terbatas.
"""

from __future__ import annotations

import os
import sys
import time
import uuid
from pathlib import Path
from typing import Callable, Sequence, TypeVar

import grpc

BASE_DIR = Path(__file__).resolve().parent
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from stubs import cinema_pb2, cinema_pb2_grpc

TResponse = TypeVar("TResponse")

DEFAULT_TARGET = os.getenv("GRPC_TARGET", "localhost:50051")
DEFAULT_TIMEOUT = 3.0
DEFAULT_MAX_RETRIES = 2
DEFAULT_BACKOFF_BASE = 0.5

_RETRYABLE_CODES = frozenset(
    {
        grpc.StatusCode.UNAVAILABLE,
        grpc.StatusCode.DEADLINE_EXCEEDED,
    }
)


class CinemaRpcClient:
    """Wrapper gRPC stub: deadline per-call + retry terbatas + backoff."""

    def __init__(
        self,
        target: str = DEFAULT_TARGET,
        timeout: float = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        backoff_base: float = DEFAULT_BACKOFF_BASE,
    ) -> None:
        self._timeout = timeout
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._channel = grpc.insecure_channel(target)
        self._stub = cinema_pb2_grpc.CinemaServiceStub(self._channel)

    def close(self) -> None:
        self._channel.close()

    # -- Pola panggilan dengan timeout + retry -----------------------------

    def _call(self, method: Callable[..., TResponse], request, *, retry: bool = True) -> TResponse:
        attempt = 0
        while True:
            try:
                return method(request, timeout=self._timeout)
            except grpc.RpcError as err:
                if (
                    not retry
                    or err.code() not in _RETRYABLE_CODES
                    or attempt >= self._max_retries
                ):
                    raise
                # Exponential backoff: 0.5s, 1s, 2s, ...
                time.sleep(self._backoff_base * (2 ** attempt))
                attempt += 1

    # -- Unary -------------------------------------------------------------

    def lihat_daftar_jadwal(self) -> cinema_pb2.LihatDaftarJadwalResponse:
        return self._call(self._stub.LihatDaftarJadwal, cinema_pb2.LihatDaftarJadwalRequest())

    def lihat_daftar_kursi(self, schedule_id: str) -> cinema_pb2.LihatDaftarKursiResponse:
        request = cinema_pb2.LihatDaftarKursiRequest(schedule_id=schedule_id)
        return self._call(self._stub.LihatDaftarKursi, request)

    def pesan_kursi(
        self,
        request_id: str,
        schedule_id: str,
        seat_ids: Sequence[str],
    ) -> cinema_pb2.PesanKursiResponse:
        request = cinema_pb2.PesanKursiRequest(
            request_id=request_id,
            schedule_id=schedule_id,
            seat_ids=seat_ids,
        )
        return self._call(self._stub.PesanKursi, request)

    def batalkan_pesanan(self, request_id: str, reservation_id: str) -> cinema_pb2.BatalkanPesananResponse:
        request = cinema_pb2.BatalkanPesananRequest(
            request_id=request_id,
            reservation_id=reservation_id,
        )
        return self._call(self._stub.BatalkanPesanan, request)

    def lihat_detail_pesanan(self, reservation_id: str) -> cinema_pb2.LihatDetailPesananResponse:
        request = cinema_pb2.LihatDetailPesananRequest(reservation_id=reservation_id)
        return self._call(self._stub.LihatDetailPesanan, request)

    # -- Server streaming (diteruskan langsung, tanpa retry) ---------------

    def stream_status_kursi(self, schedule_id: str):
        return self._stub.StreamStatusKursi(
            cinema_pb2.StreamStatusKursiRequest(schedule_id=schedule_id)
        )


def main() -> int:
    """Uji manual end-to-end: jadwal -> pesan 2 kursi -> detail -> batal -> cek kursi."""
    client = CinemaRpcClient()
    try:
        jadwal_list = client.lihat_daftar_jadwal()
        print(f"[client] {len(jadwal_list.daftar_jadwal)} jadwal, contoh:")
        for jadwal in jadwal_list.daftar_jadwal[:3]:
            print(f"[client] {jadwal.schedule_id}: {jadwal.judul} @ {jadwal.jam_tayang}")
        jadwal = jadwal_list.daftar_jadwal[0]

        daftar = client.lihat_daftar_kursi(jadwal.schedule_id)
        seats = list(daftar.daftar_kursi)
        for kursi in seats:
            print(f"[client] Kursi {kursi.id}: {cinema_pb2.StatusKursi.Name(kursi.status)}")

        kursi_bebas = next(
            (k.id for k in seats if k.status == cinema_pb2.KURSI_AVAILABLE),
            None,
        )
        if kursi_bebas is None:
            print("[client] Tidak ada kursi tersedia untuk demo")
            return 1

        # Reservasi 2 kursi sekaligus (all-or-nothing).
        kursi_lain = next(
            (k.id for k in seats if k.status == cinema_pb2.KURSI_AVAILABLE and k.id != kursi_bebas),
            None,
        )
        dipilih = [s for s in (kursi_bebas, kursi_lain) if s]
        hasil = client.pesan_kursi(str(uuid.uuid4()), jadwal.schedule_id, dipilih)
        print(
            f"[client] PesanKursi({jadwal.schedule_id}, {dipilih}) -> "
            f"success={hasil.success} ({hasil.message})"
        )
        if not hasil.success or not hasil.HasField("reservasi"):
            return 1

        reservation_id = hasil.reservasi.reservation_id
        detail = client.lihat_detail_pesanan(reservation_id)
        print("[client] Detail:", cinema_pb2.StatusReservasi.Name(detail.reservasi.status))

        batal = client.batalkan_pesanan(str(uuid.uuid4()), reservation_id)
        print(f"[client] BatalkanPesanan -> success={batal.success} ({batal.message})")

        daftar_akhir = client.lihat_daftar_kursi(jadwal.schedule_id)
        for kursi in daftar_akhir.daftar_kursi:
            if kursi.id in dipilih:
                print(f"[client] Kursi {kursi.id} sekarang: {cinema_pb2.StatusKursi.Name(kursi.status)}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
