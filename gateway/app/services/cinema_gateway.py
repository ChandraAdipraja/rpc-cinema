"""Business orchestration gateway: memanggil gRPC, memetakan ke HTTP.

Aturan: gateway TIDAK memindahkan business logic ke sini. Semua aturan
reservasi tetap dieksekusi oleh gRPC Server; layer ini hanya mapping
error/status dan pembuatan request ID per operasi logis.
"""

from __future__ import annotations

import uuid
from typing import Iterator, Optional

import grpc

from ..grpc_client.cinema_rpc import CinemaRpcClient, get_client
from ..grpc_client.loader import cinema_pb2


class GatewayError(Exception):
    """Error yang sudah dipetakan ke status HTTP oleh services layer."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


_SEAT_STATUS_NAME = {
    cinema_pb2.KURSI_AVAILABLE: "AVAILABLE",
    cinema_pb2.KURSI_RESERVED: "RESERVED",
}

_RESERVATION_STATUS_NAME = {
    cinema_pb2.RESERVASI_AKTIF: "AKTIF",
    cinema_pb2.RESERVASI_DIBATALKAN: "DIBATALKAN",
}


def _rpc_error_to_status(err: grpc.RpcError) -> int:
    code = err.code()
    if code == grpc.StatusCode.INVALID_ARGUMENT:
        return 400
    if code == grpc.StatusCode.NOT_FOUND:
        return 404
    if code in (grpc.StatusCode.UNAVAILABLE, grpc.StatusCode.DEADLINE_EXCEEDED):
        return 502
    return 500


def _jadwal_out(jadwal) -> dict:
    return {
        "schedule_id": jadwal.schedule_id,
        "judul": jadwal.judul,
        "genre": jadwal.genre,
        "durasi_menit": jadwal.durasi_menit,
        "jam_tayang": jadwal.jam_tayang,
    }


def _reservation_out(record) -> dict:
    return {
        "reservation_id": record.reservation_id,
        "schedule_id": record.schedule_id,
        "seat_ids": list(record.seat_ids),
        "status": _RESERVATION_STATUS_NAME[record.status],
    }


class CinemaGateway:
    def __init__(self, client: Optional[CinemaRpcClient] = None) -> None:
        self._client = client if client is not None else get_client()

    def daftar_jadwal(self) -> list[dict]:
        try:
            response = self._client.lihat_daftar_jadwal()
        except grpc.RpcError as err:
            raise GatewayError(_rpc_error_to_status(err), f"gRPC error: {err.details()}") from err
        return [_jadwal_out(jadwal) for jadwal in response.daftar_jadwal]

    def daftar_kursi(self, schedule_id: str) -> list[dict]:
        try:
            response = self._client.lihat_daftar_kursi(schedule_id)
        except grpc.RpcError as err:
            raise GatewayError(_rpc_error_to_status(err), f"gRPC error: {err.details()}") from err
        return [
            {"id": kursi.id, "status": _SEAT_STATUS_NAME[kursi.status]}
            for kursi in response.daftar_kursi
        ]

    def pesan_kursi(self, schedule_id: str, seat_ids: list[str]) -> dict:
        # Request ID dibuat gateway SATU kali per operasi logis; retry di
        # client gRPC tetap memakai ID yang sama sehingga sifat idempotent
        # tetap terlindungi.
        request_id = uuid.uuid4().hex
        try:
            response = self._client.pesan_kursi(request_id, schedule_id, seat_ids)
        except grpc.RpcError as err:
            raise GatewayError(_rpc_error_to_status(err), f"gRPC error: {err.details()}") from err

        payload = {"success": response.success, "message": response.message}
        if response.success:
            payload["reservasi"] = _reservation_out(response.reservasi)
            return payload
        # Business failure (ada kursi yang sudah dipesan) -> conflict, bukan 500.
        raise GatewayError(409, response.message)

    def batalkan_pesanan(self, reservation_id: str) -> dict:
        request_id = uuid.uuid4().hex
        try:
            response = self._client.batalkan_pesanan(request_id, reservation_id)
        except grpc.RpcError as err:
            raise GatewayError(_rpc_error_to_status(err), f"gRPC error: {err.details()}") from err
        return {
            "success": response.success,
            "message": response.message,
            "reservasi": _reservation_out(response.reservasi),
        }

    def detail_pesanan(self, reservation_id: str) -> dict:
        try:
            response = self._client.lihat_detail_pesanan(reservation_id)
        except grpc.RpcError as err:
            raise GatewayError(_rpc_error_to_status(err), f"gRPC error: {err.details()}") from err
        if not response.found:
            raise GatewayError(404, f"Reservasi {reservation_id} tidak ditemukan")
        return _reservation_out(response.reservasi)

    def stream_kursi(self, schedule_id: str) -> Iterator[dict]:
        """Langsung meneruskan stream gRPC satu jadwal; tanpa business logic."""
        rendez = self._client.stream_status_kursi(schedule_id)
        try:
            for update in rendez:
                kursi = update.kursi
                yield {
                    "kursi": {
                        "id": kursi.id,
                        "status": _SEAT_STATUS_NAME[kursi.status],
                    }
                }
        finally:
            rendez.cancel()


_gateway: Optional[CinemaGateway] = None


def get_gateway() -> CinemaGateway:
    global _gateway
    if _gateway is None:
        _gateway = CinemaGateway()
    return _gateway
