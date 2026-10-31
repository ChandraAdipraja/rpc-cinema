"""Client gRPC milik gateway (HTTP -> gRPC bridge).

Timeout dan retry dipakai di sini karena gateway berperan sebagai client RPC.
Retry hanya untuk operasi idempotent (punya request_id) pada
UNAVAILABLE / DEADLINE_EXCEEDED, dengan percobaan terbatas.
"""

from __future__ import annotations

import os
import time
from functools import lru_cache
from typing import Callable, Optional, TypeVar

import grpc

from .loader import cinema_pb2, cinema_pb2_grpc

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
                time.sleep(self._backoff_base * (2 ** attempt))
                attempt += 1

    def lihat_daftar_jadwal(self) -> cinema_pb2.LihatDaftarJadwalResponse:
        return self._call(self._stub.LihatDaftarJadwal, cinema_pb2.LihatDaftarJadwalRequest(), retry=False)

    def lihat_daftar_kursi(self, schedule_id: str) -> cinema_pb2.LihatDaftarKursiResponse:
        request = cinema_pb2.LihatDaftarKursiRequest(schedule_id=schedule_id)
        return self._call(self._stub.LihatDaftarKursi, request, retry=False)

    def pesan_kursi(self, request_id: str, schedule_id: str, seat_ids: list[str]) -> cinema_pb2.PesanKursiResponse:
        request = cinema_pb2.PesanKursiRequest(
            request_id=request_id,
            schedule_id=schedule_id,
            seat_ids=list(seat_ids),
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

    # Server streaming: tanpa retry, iterasi langsung diteruskan ke SSE.
    def stream_status_kursi(self, schedule_id: str):
        return self._stub.StreamStatusKursi(
            cinema_pb2.StreamStatusKursiRequest(schedule_id=schedule_id)
        )


@lru_cache(maxsize=1)
def get_client() -> CinemaRpcClient:
    """Singleton client untuk seluruh proses gateway."""
    return CinemaRpcClient()
