"""Race booking lintas dua mesin untuk demo (mis. A = server, B = client).

Jalankan skrip yang SAMA di kedua mesin dengan `--start-at` dan `--seat` yang
sama. Tiap ronde kedua mesin menembak `PesanKursi` untuk kursi yang sama;
hasil yang benar adalah tepat satu MENANG per kursi (double booking = 0).

Skrip ini TIDAK menyalakan server. Target diambil dari `--target` atau
`GRPC_TARGET` (mis. komputer B memakai `<IP-A>:50051`).

Urutan kursi mengikuti `--seat` sebagai kursi awal:
A1, A2, A3, B1, B2, B3 (berputar kembali ke awal bila ronde > 6).

Contoh (jam kedua mesin harus sinkron, mis. `w32tm /resync`):

    # Komputer A
    python load_test/race_two_devices.py --label A --seat A1 --rounds 6 --start-at 20:15:00

    # Komputer B
    python load_test/race_two_devices.py --target <IP-A>:50051 --label B --seat A1 --rounds 6 --start-at 20:15:00

"Serempak" berarti selisih puluhan milidetik, tergantung sinkronisasi jam dan
jaringan; ini bukan pengukuran presisi, melainkan bukti tidak ada double
booking saat dua mesin mencoba kursi yang sama.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import socket
import sys
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "grpc_server") not in sys.path:
    sys.path.insert(0, str(ROOT / "grpc_server"))

import grpc

from cinema_client import CinemaRpcClient
from stubs import cinema_pb2

SEAT_ORDER = ("A1", "A2", "A3", "B1", "B2", "B3")
RESULTS_DIR = Path(__file__).resolve().parent / "results"

MENANG = "MENANG"
KONFLIK = "KONFLIK"
ERROR_PREFIX = "ERROR"


@dataclass
class RoundResult:
    round: int
    label: str
    seat: str
    fired_at: str
    outcome: str
    latency_ms: float
    request_id: str
    reservation_id: str | None = None
    detail: str | None = None


def parse_start_at(value: str) -> datetime:
    """Parse HH:MM:SS lokal menjadi datetime hari ini."""
    try:
        jam = datetime.strptime(value, "%H:%M:%S").time()
    except ValueError as err:
        raise argparse.ArgumentTypeError(
            f"format --start-at harus HH:MM:SS (contoh 20:15:00), bukan {value!r}"
        ) from err
    return datetime.combine(date.today(), jam)


def seat_sequence(start_seat: str, rounds: int) -> list[str]:
    """Urutan kursi mulai dari `start_seat`, berputar pada SEAT_ORDER."""
    start_seat = start_seat.upper()
    if start_seat not in SEAT_ORDER:
        raise ValueError(
            f"--seat {start_seat!r} tidak dikenal; pilihan: {', '.join(SEAT_ORDER)}"
        )
    if rounds < 1:
        raise ValueError("--rounds minimal 1")
    awal = SEAT_ORDER.index(start_seat)
    return [SEAT_ORDER[(awal + i) % len(SEAT_ORDER)] for i in range(rounds)]


def wait_until(target: datetime) -> None:
    """Tunggu sampai waktu target; 50 ms terakhir memakai polling rapat."""
    while True:
        remaining = (target - datetime.now()).total_seconds()
        if remaining <= 0:
            return
        if remaining > 0.05:
            time.sleep(remaining - 0.05)
        else:
            time.sleep(0.001)


def _safe_label(label: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", label) or "client"


def fire_round(
    client: CinemaRpcClient, schedule_id: str, seat: str, label: str, round_index: int
) -> RoundResult:
    """Tembak satu PesanKursi dan klasifikasikan hasilnya."""
    request_id = uuid.uuid4().hex
    started = time.perf_counter()
    try:
        response = client.pesan_kursi(request_id, schedule_id, [seat])
    except grpc.RpcError as err:
        latensi = (time.perf_counter() - started) * 1000.0
        return RoundResult(
            round=round_index,
            label=label,
            seat=seat,
            fired_at=datetime.now().strftime("%H:%M:%S.%f")[:-3],
            outcome=f"{ERROR_PREFIX} {err.code().name}",
            latency_ms=latensi,
            request_id=request_id,
            detail=err.details(),
        )

    latensi = (time.perf_counter() - started) * 1000.0
    if response.success:
        outcome = MENANG
        reservation_id = response.reservasi.reservation_id
        detail = response.message
    else:
        outcome = KONFLIK
        reservation_id = None
        detail = response.message
    return RoundResult(
        round=round_index,
        label=label,
        seat=seat,
        fired_at=datetime.now().strftime("%H:%M:%S.%f")[:-3],
        outcome=outcome,
        latency_ms=latensi,
        request_id=request_id,
        reservation_id=reservation_id,
        detail=detail,
    )


def summarize(results: list[RoundResult]) -> dict:
    menang = sum(1 for r in results if r.outcome == MENANG)
    konflik = sum(1 for r in results if r.outcome == KONFLIK)
    error = sum(1 for r in results if r.outcome.startswith(ERROR_PREFIX))
    latencies = [r.latency_ms for r in results]
    return {
        "rounds": len(results),
        "menang": menang,
        "konflik": konflik,
        "error": error,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 3) if latencies else 0.0,
    }


def build_payload(
    label: str,
    target: str,
    schedule_id: str,
    start_at: str | None,
    results: list[RoundResult],
) -> dict:
    return {
        "label": label,
        "target": target,
        "schedule_id": schedule_id,
        "start_at": start_at,
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "rounds": [asdict(result) for result in results],
        "summary": summarize(results),
    }


def save_results(path: Path, payload: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return path


def _check_seats_available(
    client: CinemaRpcClient, schedule_id: str, seats: list[str]
) -> None:
    daftar = client.lihat_daftar_kursi(schedule_id)
    status = {kursi.id: kursi.status for kursi in daftar.daftar_kursi}
    tidak_ada = [seat for seat in seats if seat not in status]
    if tidak_ada:
        raise RuntimeError(f"kursi tidak ada di jadwal {schedule_id}: {', '.join(tidak_ada)}")
    terisi = [
        seat for seat in seats if status[seat] != cinema_pb2.KURSI_AVAILABLE
    ]
    if terisi:
        raise RuntimeError(
            "kursi sudah terisi sebelum race: "
            + ", ".join(terisi)
            + ". Pilih --seat lain atau restart server agar state bersih."
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Race booking lintas mesin. Jalankan skrip yang sama di dua mesin "
            "dengan --start-at dan --seat yang sama."
        )
    )
    parser.add_argument(
        "--target",
        default=os.getenv("GRPC_TARGET", "localhost:50051"),
        help="host:port server gRPC (default: GRPC_TARGET atau localhost:50051)",
    )
    parser.add_argument(
        "--schedule-id",
        default=None,
        help="jadwal yang dipakai (default: jadwal pertama dari server)",
    )
    parser.add_argument(
        "--seat",
        default="A1",
        help=(
            "kursi awal urutan ronde; urutan tetap A1,A2,A3,B1,B2,B3 "
            "berputar kembali ke awal (default: A1)"
        ),
    )
    parser.add_argument(
        "--start-at",
        type=parse_start_at,
        default=None,
        help="waktu lokal HH:MM:SS untuk menembak ronde pertama (default: langsung)",
    )
    parser.add_argument(
        "--label",
        default=socket.gethostname(),
        help="nama mesin pada log/JSON (mis. A atau B; default: hostname)",
    )
    parser.add_argument(
        "--rounds", type=int, default=1, help="jumlah ronde (default: 1)"
    )
    args = parser.parse_args(argv)

    try:
        seats = seat_sequence(args.seat, args.rounds)
    except ValueError as err:
        parser.error(str(err))

    target = args.target.strip()
    if not target:
        print("[race] target kosong; isi --target atau GRPC_TARGET")
        return 2

    if args.start_at is not None:
        sisa = (args.start_at - datetime.now()).total_seconds()
        if sisa < -1.0:
            print(
                f"[race] --start-at {args.start_at.strftime('%H:%M:%S')} sudah lewat. "
                "Pilih waktu berikutnya (skrip tidak menunggu sampai besok)."
            )
            return 2

    if len(seats) > len(SEAT_ORDER):
        print(
            f"[race] peringatan: {len(seats)} ronde > {len(SEAT_ORDER)} kursi; "
            "kursi akan dipakai ulang dan kemungkinan sudah terisi."
        )

    client = CinemaRpcClient(target=target, timeout=5.0, max_retries=2)
    try:
        try:
            if args.schedule_id:
                schedule_id = args.schedule_id
            else:
                schedule_id = client.lihat_daftar_jadwal().daftar_jadwal[0].schedule_id
            _check_seats_available(client, schedule_id, sorted(set(seats)))
        except (grpc.RpcError, RuntimeError) as err:
            print(f"[race] GAGAL preflight: {err}")
            print(
                "[race] Periksa: server hidup, target benar, firewall TCP 50051, "
                "dan kursi belum terisi."
            )
            return 1

        print(
            f"[race] label={args.label} target={target} schedule={schedule_id} "
            f"rounds={len(seats)} seats={','.join(seats)}"
        )
        if args.start_at is not None:
            print(f"[race] menunggu {args.start_at.strftime('%H:%M:%S')} ...")
            wait_until(args.start_at)

        results: list[RoundResult] = []
        for index, seat in enumerate(seats, start=1):
            hasil = fire_round(client, schedule_id, seat, args.label, index)
            results.append(hasil)
            print(
                f"[race] {hasil.label} {hasil.fired_at} {seat} "
                f"{hasil.outcome} {hasil.latency_ms:.1f}ms"
            )

        ringkasan = summarize(results)
        print(
            f"[race] ringkasan label={args.label}: ronde={ringkasan['rounds']} "
            f"menang={ringkasan['menang']} konflik={ringkasan['konflik']} "
            f"error={ringkasan['error']} avg={ringkasan['avg_latency_ms']:.1f}ms"
        )

        payload = build_payload(
            args.label,
            target,
            schedule_id,
            args.start_at.strftime("%H:%M:%S") if args.start_at else None,
            results,
        )
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path = RESULTS_DIR / f"race_{_safe_label(args.label)}_{stamp}.json"
        save_results(path, payload)
        print(f"[race] JSON: {path}")
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    sys.exit(main())
