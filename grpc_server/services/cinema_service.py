"""Implementasi gRPC service CinemaService.

Tugas layer ini hanya mapping domain <-> Protocol Buffers dan orkestrasi
idempotency; business logic reservasi ada di core.storage, transport ada
pada framework gRPC itu sendiri.
"""

from __future__ import annotations

import grpc

from core.idempotency import (
    IdempotencyConflict,
    IdempotencyStore,
    OpResult,
    booking_fingerprint,
    cancel_fingerprint,
)
from core.locking import StateLock
from core.storage import (
    RESERVATION_ACTIVE,
    SEAT_AVAILABLE,
    SEAT_RESERVED,
    CinemaState,
    ReservationNotFoundError,
    ReservationRecord,
    ScheduleNotFoundError,
    SeatNotFoundError,
    SeatUnavailableError,
)
from stubs import cinema_pb2, cinema_pb2_grpc

PESAN_OP = "pesan"
BATALKAN_OP = "batalkan"

# Batas wajar untuk idempotency key dari klien; UUID hanya 36 karakter.
_MAX_REQUEST_ID_LENGTH = 128

# Polling kecil: setiap mutasi menaikkan version dan membangunkan listener
# lewat Condition, jadi polling timeout hanya dipakai untuk memeriksa
# client yang terputus.
_STREAM_IDLE_POLL_SECONDS = 1.0

_SEAT_STATUS_ENUM = {
    SEAT_AVAILABLE: cinema_pb2.KURSI_AVAILABLE,
    SEAT_RESERVED: cinema_pb2.KURSI_RESERVED,
}


def _jadwal_message(schedule) -> cinema_pb2.Jadwal:
    return cinema_pb2.Jadwal(
        schedule_id=schedule.schedule_id,
        judul=schedule.judul,
        genre=schedule.genre,
        durasi_menit=schedule.durasi_menit,
        jam_tayang=schedule.jam_tayang,
    )


def _reservation_message(
    record: ReservationRecord,
) -> cinema_pb2.Reservation:
    status = (
        cinema_pb2.RESERVASI_AKTIF
        if record.status == RESERVATION_ACTIVE
        else cinema_pb2.RESERVASI_DIBATALKAN
    )
    return cinema_pb2.Reservation(
        reservation_id=record.reservation_id,
        schedule_id=record.schedule_id,
        seat_ids=record.seat_ids,
        status=status,
    )


def _pesan_response(result: OpResult) -> cinema_pb2.PesanKursiResponse:
    return cinema_pb2.PesanKursiResponse(
        success=result.success,
        message=result.message,
        reservasi=None if result.reservation is None else _reservation_message(result.reservation),
    )


def _batalkan_response(result: OpResult) -> cinema_pb2.BatalkanPesananResponse:
    return cinema_pb2.BatalkanPesananResponse(
        success=result.success,
        message=result.message,
        reservasi=None if result.reservation is None else _reservation_message(result.reservation),
    )


def _require_request_id(request_id: str, context) -> None:
    if not request_id:
        context.abort(grpc.StatusCode.INVALID_ARGUMENT, "request_id wajib diisi")
    if len(request_id) > _MAX_REQUEST_ID_LENGTH:
        context.abort(
            grpc.StatusCode.INVALID_ARGUMENT,
            f"request_id maksimal {_MAX_REQUEST_ID_LENGTH} karakter",
        )


class CinemaService(cinema_pb2_grpc.CinemaServiceServicer):
    def __init__(
        self,
        state: CinemaState,
        idempotency: IdempotencyStore,
        state_lock: StateLock,
    ) -> None:
        self._state = state
        self._idempotency = idempotency
        self._state_lock = state_lock

    # -- Unary ------------------------------------------------------------

    def LihatDaftarJadwal(self, request, context):
        daftar_jadwal = [_jadwal_message(s) for s in self._state.daftar_jadwal()]
        return cinema_pb2.LihatDaftarJadwalResponse(daftar_jadwal=daftar_jadwal)

    def LihatDaftarKursi(self, request, context):
        if not request.schedule_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "schedule_id wajib diisi")
        try:
            snapshot = self._state.snapshot(request.schedule_id)
        except ScheduleNotFoundError:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Jadwal {request.schedule_id} tidak ditemukan",
            )
        daftar_kursi = [
            cinema_pb2.Kursi(id=seat_id, status=_SEAT_STATUS_ENUM[status])
            for seat_id, status in snapshot
        ]
        return cinema_pb2.LihatDaftarKursiResponse(
            schedule_id=request.schedule_id,
            daftar_kursi=daftar_kursi,
        )

    def PesanKursi(self, request, context):
        _require_request_id(request.request_id, context)
        if not request.schedule_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "schedule_id wajib diisi")
        if not request.seat_ids:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "seat_ids minimal satu kursi")
        # Kursi dobel di satu request tidak masuk akal secara bisnis.
        if len(set(request.seat_ids)) != len(request.seat_ids):
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                "seat_ids tidak boleh mengandung kursi ganda",
            )

        # Validasi tetap dijalankan sebelum cache: retry dengan payload identik
        # selalu lolos validasi yang sama, sedangkan payload berubah tetap
        # ditolak tanpa melemahkan aturan input.
        try:
            known_seats = set(self._state.seat_ids(request.schedule_id))
        except ScheduleNotFoundError:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Jadwal {request.schedule_id} tidak ditemukan",
            )
        unknown = [seat_id for seat_id in request.seat_ids if seat_id not in known_seats]
        if unknown:
            context.abort(
                grpc.StatusCode.INVALID_ARGUMENT,
                f"Kursi {', '.join(unknown)} tidak dikenal pada jadwal {request.schedule_id}",
            )

        fingerprint = booking_fingerprint(PESAN_OP, request.schedule_id, request.seat_ids)

        with self._state_lock.hold():
            try:
                cached = self._idempotency.get(PESAN_OP, request.request_id, fingerprint)
            except IdempotencyConflict:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    f"request_id {request.request_id} sudah dipakai untuk permintaan "
                    "dengan payload berbeda",
                )
            if cached is not None:
                return _pesan_response(cached)

            try:
                record = self._state.reserve(request.schedule_id, request.seat_ids)
            except SeatUnavailableError as err:
                # Konflik belum menghasilkan reservasi, jadi tidak disimpan:
                # percobaan ulang boleh berhasil setelah kursi dibebaskan.
                return _pesan_response(
                    OpResult(success=False, message=str(err), reservation=None)
                )
            result = OpResult(success=True, message="Reservasi berhasil", reservation=record)
            self._idempotency.save(PESAN_OP, request.request_id, fingerprint, result)

        return _pesan_response(result)

    def BatalkanPesanan(self, request, context):
        _require_request_id(request.request_id, context)
        if not request.reservation_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "reservation_id wajib diisi")

        fingerprint = cancel_fingerprint(BATALKAN_OP, request.reservation_id)

        with self._state_lock.hold():
            try:
                cached = self._idempotency.get(BATALKAN_OP, request.request_id, fingerprint)
            except IdempotencyConflict:
                context.abort(
                    grpc.StatusCode.FAILED_PRECONDITION,
                    f"request_id {request.request_id} sudah dipakai untuk permintaan "
                    "dengan payload berbeda",
                )
            if cached is not None:
                return _batalkan_response(cached)

            try:
                record = self._state.cancel(request.reservation_id)
            except ReservationNotFoundError:
                context.abort(
                    grpc.StatusCode.NOT_FOUND,
                    f"Reservasi {request.reservation_id} tidak ditemukan",
                )
            result = OpResult(success=True, message="Reservasi berhasil dibatalkan", reservation=record)
            self._idempotency.save(BATALKAN_OP, request.request_id, fingerprint, result)

        return _batalkan_response(result)

    def LihatDetailPesanan(self, request, context):
        if not request.reservation_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "reservation_id wajib diisi")

        record = self._state.get_reservation(request.reservation_id)
        if record is None:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Reservasi {request.reservation_id} tidak ditemukan",
            )
        return cinema_pb2.LihatDetailPesananResponse(
            found=True,
            reservasi=_reservation_message(record),
        )

    # -- Server streaming --------------------------------------------------

    def StreamStatusKursi(self, request, context):
        if not request.schedule_id:
            context.abort(grpc.StatusCode.INVALID_ARGUMENT, "schedule_id wajib diisi")
        if self._state.get_schedule(request.schedule_id) is None:
            context.abort(
                grpc.StatusCode.NOT_FOUND,
                f"Jadwal {request.schedule_id} tidak ditemukan",
            )

        last_version = self._state.schedule_version(request.schedule_id)
        for seat_id, status in self._state.snapshot(request.schedule_id):
            yield cinema_pb2.KursiUpdate(
                kursi=cinema_pb2.Kursi(id=seat_id, status=_SEAT_STATUS_ENUM[status])
            )

        # Loop hanya hidup selama subscriber masih terhubung; menangani
        # client yang terputus via context.is_active() di setiap interval.
        try:
            while context.is_active():
                version = self._state.wait_for_change(
                    request.schedule_id, last_version, _STREAM_IDLE_POLL_SECONDS
                )
                if version == last_version:
                    continue
                last_version = version
                for seat_id, status in self._state.snapshot(request.schedule_id):
                    yield cinema_pb2.KursiUpdate(
                        kursi=cinema_pb2.Kursi(id=seat_id, status=_SEAT_STATUS_ENUM[status])
                    )
        except grpc.RpcError:
            # Client terputus; tidak ada resource yang perlu dirapikan.
            return
