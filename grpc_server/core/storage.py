"""In-memory storage untuk jadwal, kursi, dan reservasi cinema.

Kursi bersifat unik per jadwal: {schedule_id: {seat_id: status}}. Memesan
banyak kursi bersifat all-or-nothing — seluruh kursi dicek dulu, baru
semuanya dikunci dalam satu critical section (tidak ada partial booking).
Perubahan state menaikkan version dan membangunkan subscriber streaming.
"""

from __future__ import annotations

import threading
import time
import typing
import uuid
from dataclasses import dataclass

SEAT_AVAILABLE = "AVAILABLE"
SEAT_RESERVED = "RESERVED"

RESERVATION_ACTIVE = "ACTIVE"
RESERVATION_CANCELLED = "CANCELLED"


class CinemaStateError(Exception):
    """Kesalahan domain saat operasi reservasi."""


class ScheduleNotFoundError(CinemaStateError):
    pass


class SeatNotFoundError(CinemaStateError):
    pass


class SeatUnavailableError(CinemaStateError):
    pass


class ReservationNotFoundError(CinemaStateError):
    pass


@dataclass(frozen=True)
class Schedule:
    schedule_id: str
    judul: str
    genre: str
    durasi_menit: int
    jam_tayang: str


@dataclass
class ReservationRecord:
    reservation_id: str
    schedule_id: str
    seat_ids: typing.Tuple[str, ...]
    status: str
    created_at: float


class CinemaState:
    """Single source of truth untuk jadwal, kursi, reservasi, dan versi perubahan."""

    def __init__(
        self,
        lock: threading.RLock,
        schedules: typing.Sequence[Schedule],
        seat_ids: typing.Sequence[str],
    ) -> None:
        self._cond = threading.Condition(lock)
        self._schedules: dict[str, Schedule] = {s.schedule_id: s for s in schedules}
        self._seats: dict[str, dict[str, str]] = {
            schedule.schedule_id: {seat_id: SEAT_AVAILABLE for seat_id in seat_ids}
            for schedule in schedules
        }
        self._reservations: dict[str, ReservationRecord] = {}
        # Versi per jadwal: subscriber satu jadwal tidak dibangunkan oleh
        # perubahan pada jadwal lain.
        self._schedule_versions: dict[str, int] = {s.schedule_id: 0 for s in schedules}

    # -- Jadwal -----------------------------------------------------------

    def daftar_jadwal(self) -> typing.List[Schedule]:
        with self._cond:
            return list(self._schedules.values())

    def get_schedule(self, schedule_id: str) -> typing.Optional[Schedule]:
        with self._cond:
            return self._schedules.get(schedule_id)

    def seat_ids(self, schedule_id: str) -> typing.Tuple[str, ...]:
        """Daftar kursi milik sebuah jadwal; error bila jadwal tidak dikenal."""
        with self._cond:
            seats = self._seats.get(schedule_id)
            if seats is None:
                raise ScheduleNotFoundError(f"Jadwal {schedule_id} tidak dikenal")
            return tuple(seats)

    # -- Kursi ------------------------------------------------------------

    def snapshot(self, schedule_id: str) -> typing.List[typing.Tuple[str, str]]:
        """Salinan ringan status seluruh kursi satu jadwal pada satu momen."""
        with self._cond:
            seats = self._seats.get(schedule_id)
            if seats is None:
                raise ScheduleNotFoundError(f"Jadwal {schedule_id} tidak dikenal")
            return list(seats.items())

    def reserve(self, schedule_id: str, seat_ids: typing.Sequence[str]) -> ReservationRecord:
        """Kunci beberapa kursi sekaligus; gagal seluruhnya bila ada yang tidak tersedia."""
        with self._cond:
            seats = self._seats.get(schedule_id)
            if seats is None:
                raise ScheduleNotFoundError(f"Jadwal {schedule_id} tidak dikenal")

            unknown = [seat_id for seat_id in seat_ids if seat_id not in seats]
            if unknown:
                raise SeatNotFoundError(f"Kursi {', '.join(unknown)} tidak dikenal")

            taken = [seat_id for seat_id in seat_ids if seats[seat_id] != SEAT_AVAILABLE]
            if taken:
                raise SeatUnavailableError(f"Kursi {', '.join(taken)} sudah dipesan")

            # Cek dan update dalam satu blok kunci: all-or-nothing.
            for seat_id in seat_ids:
                seats[seat_id] = SEAT_RESERVED

            record = ReservationRecord(
                reservation_id=uuid.uuid4().hex,
                schedule_id=schedule_id,
                seat_ids=tuple(seat_ids),
                status=RESERVATION_ACTIVE,
                created_at=time.time(),
            )
            self._reservations[record.reservation_id] = record
            self._schedule_versions[schedule_id] += 1
            self._cond.notify_all()
            return record

    def cancel(self, reservation_id: str) -> ReservationRecord:
        """Batalkan reservasi; seluruh kursinya dibebaskan (idempotent di domain)."""
        with self._cond:
            record = self._reservations.get(reservation_id)
            if record is None:
                raise ReservationNotFoundError(f"Reservasi {reservation_id} tidak ditemukan")

            if record.status != RESERVATION_ACTIVE:
                return record

            record.status = RESERVATION_CANCELLED
            seats = self._seats[record.schedule_id]
            for seat_id in record.seat_ids:
                seats[seat_id] = SEAT_AVAILABLE
            self._schedule_versions[record.schedule_id] += 1
            self._cond.notify_all()
            return record

    # -- Reservasi ----------------------------------------------------------

    def get_reservation(self, reservation_id: str) -> typing.Optional[ReservationRecord]:
        with self._cond:
            record = self._reservations.get(reservation_id)
            if record is None:
                return None
            return ReservationRecord(
                reservation_id=record.reservation_id,
                schedule_id=record.schedule_id,
                seat_ids=record.seat_ids,
                status=record.status,
                created_at=record.created_at,
            )

    # -- Streaming ----------------------------------------------------------

    def schedule_version(self, schedule_id: str) -> int:
        with self._cond:
            return self._schedule_versions[schedule_id]

    def wait_for_change(self, schedule_id: str, last_version: int, timeout: float) -> int:
        """Tunggu sampai versi jadwal ini berubah; kembalikan versi terkini."""
        with self._cond:
            if self._schedule_versions[schedule_id] != last_version:
                return self._schedule_versions[schedule_id]
            self._cond.wait(timeout)
            return self._schedule_versions[schedule_id]
