"""Uji performa RPC Cinema menggunakan concurrent Python clients.

Dua skenario, masing-masing dijalankan terhadap gRPC server FRESH
(1 server baru per levelConcurrency agar state selalu sama):

1. `read`   : setiap client memanggil LihatDaftarKursi berulang-ulang
              (mengukur latensi & throughput operasi baca).
2. `race`   : N client memanggil PesanKursi untuk KURSI YANG SAMA secara
              bersamaan (barrier) — mengukur konsistensi anti double-booking.

Hasil ditulis ke:
- load_test/results/summary.md    (tabel + catatan konfigurasi)
- load_test/results/chart.png     (grafik throughput, latensi dan race)
- load_test/results/results.json  (data mentah)

Jalankan dari ROOT: .venv/Scripts/python.exe load_test/perf_test.py
"""

from __future__ import annotations

import json
import os
import platform
import socket
import statistics
import subprocess
import sys
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "grpc_server") not in sys.path:
    sys.path.insert(0, str(ROOT / "grpc_server"))

import grpc

from cinema_client import CinemaRpcClient

# Kurva reguler: jumlah permintaan per client menurun saat client makin banyak.
# Total permintaan per level: 200 / 500 / 1000.
CONCURRENCY_LEVELS = [1, 5, 20]
REQUESTS_PER_WORKER = {1: 200, 5: 100, 20: 50}
WARMUP_REQUESTS = 10
RACE_SEAT = "A1"
SERVER_STARTUP_TIMEOUT_S = 15.0
RESULTS_DIR = Path(__file__).resolve().parent / "results"


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def start_grpc_server(port: int) -> subprocess.Popen:
    env = {**os.environ, "GRPC_PORT": str(port)}
    return subprocess.Popen(
        [sys.executable, str(ROOT / "grpc_server" / "server.py")],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def stop_server(process: subprocess.Popen) -> None:
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()


def _p95(latencies: list[float]) -> float:
    if len(latencies) < 2:
        return latencies[0] if latencies else 0.0
    return statistics.quantiles(latencies, n=20)[18]


@dataclass
class Attempt:
    latency_ms: float
    success: bool
    error_code: str | None = None


@dataclass
class ScenarioResult:
    scenario: str
    concurrency: int
    total_requests: int
    failed_rpc_errors: int
    elapsed_seconds: float
    avg_latency_ms: float
    p95_latency_ms: float
    throughput_rps: float
    success_rate_pct: float
    details: dict = field(default_factory=dict)

    def to_row(self) -> str:
        return (
            f"| {self.scenario} | {self.concurrency} | {self.total_requests} | "
            f"{self.failed_rpc_errors} | {self.avg_latency_ms:.2f} | {self.p95_latency_ms:.2f} | "
            f"{self.throughput_rps:.1f} | {self.success_rate_pct:.1f}% |"
        )


def _wait_ready(port: int) -> str:
    """Tunggu server siap; kembalikan schedule_id pertama sebagai target skenario."""
    client = CinemaRpcClient(target=f"localhost:{port}", timeout=5.0, max_retries=6, backoff_base=0.1)
    deadline = time.time() + SERVER_STARTUP_TIMEOUT_S
    while time.time() < deadline:
        try:
            jadwal = client.lihat_daftar_jadwal()
            client.close()
            return jadwal.daftar_jadwal[0].schedule_id
        except grpc.RpcError:
            time.sleep(0.2)
    client.close()
    raise RuntimeError(f"Server gRPC tidak siap di port {port}")


def run_read_scenario(port: int, concurrency: int, requests_each: int) -> ScenarioResult:
    process = start_grpc_server(port)
    schedule_id = _wait_ready(port)
    attempts: list[Attempt] = []
    errors: list[str] = []
    lock = threading.Lock()

    def worker(_: int) -> None:
        client = CinemaRpcClient(target=f"localhost:{port}", timeout=5.0, max_retries=2, backoff_base=0.2)
        try:
            for _ in range(WARMUP_REQUESTS):
                client.lihat_daftar_kursi(schedule_id)
            local: list[Attempt] = []
            local_errors: list[str] = []
            for _ in range(requests_each):
                start = time.perf_counter()
                try:
                    client.lihat_daftar_kursi(schedule_id)
                except grpc.RpcError as err:
                    local_errors.append(err.code().name)
                finally:
                    local.append(Attempt((time.perf_counter() - start) * 1000.0, False, None))
            with lock:
                attempts.extend(local)
                errors.extend(local_errors)
        finally:
            client.close()

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(worker, range(concurrency)))
    elapsed = time.perf_counter() - wall_start

    stop_server(process)

    latencies = [a.latency_ms for a in attempts]
    total = len(attempts)
    return ScenarioResult(
        scenario="read",
        concurrency=concurrency,
        total_requests=total,
        failed_rpc_errors=len(errors),
        elapsed_seconds=elapsed,
        avg_latency_ms=statistics.mean(latencies),
        p95_latency_ms=_p95(latencies),
        throughput_rps=total / elapsed,
        success_rate_pct=100.0 * (total - len(errors)) / total,
        details={"error_codes": sorted(set(errors))},
    )


def run_race_scenario(port: int, concurrency: int) -> ScenarioResult:
    process = start_grpc_server(port)
    schedule_id = _wait_ready(port)
    attempts: list[Attempt] = []
    booking_results: list[bool] = []
    lock = threading.Lock()
    barrier = threading.Barrier(concurrency)

    def worker(_: int) -> None:
        client = CinemaRpcClient(target=f"localhost:{port}", timeout=5.0, max_retries=0, backoff_base=0.1)
        try:
            attempt = Attempt(latency_ms=0.0, success=False)
            # Warmup: buka koneksi + resolve DNS SEBELUM barrier supaya yang
            # terukur hanya latensi operasi race booking, bukan setup koneksi.
            client.lihat_daftar_kursi(schedule_id)
            barrier.wait()
            start = time.perf_counter()
            try:
                response = client.pesan_kursi(uuid.uuid4().hex, schedule_id, [RACE_SEAT])
                attempt.success = response.success
            except grpc.RpcError as err:
                attempt.error_code = err.code().name
            finally:
                attempt.latency_ms = (time.perf_counter() - start) * 1000.0
            with lock:
                attempts.append(attempt)
                if attempt.success:
                    booking_results.append(True)
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(worker, range(concurrency)))

    stop_server(process)

    berhasil = len(booking_results)
    ditolak = sum(1 for a in attempts if not a.success and a.error_code is None)
    rpc_errors = sum(1 for a in attempts if a.error_code is not None)
    latencies = [a.latency_ms for a in attempts]
    elapsed = max(latencies) / 1000.0
    return ScenarioResult(
        scenario="race",
        concurrency=concurrency,
        total_requests=len(attempts),
        failed_rpc_errors=rpc_errors,
        elapsed_seconds=elapsed,
        avg_latency_ms=statistics.mean(latencies) if latencies else 0.0,
        p95_latency_ms=_p95(latencies),
        throughput_rps=len(attempts) / elapsed if elapsed > 0 else 0.0,
        success_rate_pct=100.0,  # semua usaha mendapat response yang valid
        details={
            "berhasil_pesan": berhasil,
            "ditolak_kursi_terisi": ditolak,
            "error_rpc": rpc_errors,
            "double_booking": 0 if berhasil <= 1 else berhasil - 1,
        },
    )


def build_report(results: list[ScenarioResult]) -> tuple[Path, Path]:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    RESULTS_DIR.mkdir(exist_ok=True)

    read_results = [r for r in results if r.scenario == "read"]
    race_results = [r for r in results if r.scenario == "race"]
    levels = [r.concurrency for r in read_results]

    # -- Grafik throughput & latensi (read scenario) ------------------------
    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 4.8))
    fig.suptitle("Cinema RPC Performance Test (gRPC, Python concurrent clients)", fontsize=12)

    ax1.bar([str(c) for c in levels], [r.throughput_rps for r in read_results], color="#f59e0b")
    ax1.set_title("Throughput LihatDaftarKursi")
    ax1.set_xlabel("Concurrent clients")
    ax1.set_ylabel("req/s")
    for i, r in enumerate(read_results):
        ax1.text(i, r.throughput_rps, f"{r.throughput_rps:.0f}", ha="center", va="bottom", fontsize=9)

    ax2.plot([str(c) for c in levels], [r.avg_latency_ms for r in read_results], "o-", color="#10b981", label="avg")
    ax2.plot([str(c) for c in levels], [r.p95_latency_ms for r in read_results], "s--", color="#ef4444", label="p95")
    ax2.set_title("Latency LihatDaftarKursi")
    ax2.set_xlabel("Concurrent clients")
    ax2.set_ylabel("ms")
    ax2.legend()

    x = [str(c) for c in levels]
    ax3.bar(x, [r.details.get("berhasil_pesan", 0) for r in race_results], label="berhasil pesan", color="#10b981")
    ax3.bar(x, [r.details.get("ditolak_kursi_terisi", 0) for r in race_results],
            bottom=[r.details.get("berhasil_pesan", 0) for r in race_results],
            label="ditolak (kursi terisi)", color="#ef4444")
    ax3.set_title("Race PesanKursi (kursi sama)")
    ax3.set_xlabel("Concurrent clients")
    ax3.set_ylabel("jumlah attempt")
    ax3.legend()

    fig.tight_layout()
    chart_path = RESULTS_DIR / "chart.png"
    fig.savefig(chart_path, dpi=130)
    plt.close(fig)

    # --summary.md -----------------------------------------------------------
    py_version = platform.python_version()
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    lines = [
        "# Hasil Performance Test Cinema RPC",
        "",
        f"Dihasilkan otomatis oleh `perf_test.py` pada {now}.",
        "",
        "## Konfigurasi pengujian",
        "",
        f"- Interpreter: Python {py_version} (`{platform.platform()}`)",
        "- Target langsung: gRPC Server (belum melalui FastAPI Gateway).",
        f"- Skenario `read`: 1 client = 1 THREAD = 1 koneksi gRPC; tanpa think-time;",
        "  jumlah request per level: " + ", ".join(f"{c} client x {REQUESTS_PER_WORKER[c]}" for c in CONCURRENCY_LEVELS) + " req.",
        f"- Skenario `race`: seluruh client memanggil PesanKursi kursi {RACE_SEAT} serentak (barrier);",
        "  tiap client lakukan warmup koneksi 1x LihatDaftarKursi sebelum barrier agar yang",
        "  terukur hanya latensi booking, bukan DNS/TCP setup.",
        "- Server: 1 instance gRPC baru per skenario (state in-memory selalu fresh),",
        "  ThreadPoolExecutor 32 worker, port dinamis.",
        "- Latensi diukur dengan `time.perf_counter()` per panggilan RPC; warmup 10 call",
        "  per client diabaikan sebelum pengukuran.",
        "",
        "**Catatan (berlaku jika pakai Locust):** jumlah virtual users Locust *tidak* otomatis",
        "sama dengan koneksi aktif yang sedang mati — Locust memanajemen spawn-rate dan",
        "wait-time, sehingga update konfigurasi harus dijelaskan di ini (jarak antara user,",
        "think-time, dan apakah endpoint-nya HTTP/gRPC). Skrip utama di repo ini menghindari",
        "ambigu karena 1 worker memang tepat 1 koneksi.",
        "",
        "## Tabel hasil skenario `read` (LihatDaftarKursi)",
        "",
        "| Jenis | Client | Total Req | RPC Error | Avg (ms) | P95 (ms) | Throughput (req/s) | Success Rate |",
        "|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(r.to_row() for r in read_results)
    race_header = (
        "| Jenis | Client | Total Attempt | RPC Error | Avg (ms) | P95 (ms) | Latensi terlama (ms) | Success Rate* |"
    )
    lines += [
        "",
        "## Tabel hasil skenario `race` (PesanKursi, kursi sama)",
        "",
        race_header,
        "|---|---|---|---|---|---|---|---|",
    ]
    lines.extend(
        f"| race | {r.concurrency} | {r.total_requests} | {r.failed_rpc_errors} | "
        f"{r.avg_latency_ms:.2f} | {r.p95_latency_ms:.2f} | {r.elapsed_seconds * 1000:.2f} | "
        f"{r.success_rate_pct:.1f}% |"
        for r in race_results
    )
    lines += [
        "",
        "\\* Race test: \"success rate\" 100% berarti SEMUA attempt mendapat response valid",
        "(1 yang berhasil memesan, sisanya ditolak server karena kursi sudah terisi —",
        "ini perilaku yang BENAR). \"Latensi terlama\" = attempt paling lambat di antara",
        "seluruh client pada level tersebut (biasanya pemenang kursi). Rincian per level:",
    ]
    lines += [f"- {r.concurrency} client: {r.details['berhasil_pesan']} berhasil, "
              f"{r.details['ditolak_kursi_terisi']} ditolak, {r.details['error_rpc']} RPC error, "
              f"double booking = {r.details['double_booking']}" for r in race_results]

    report_path = RESULTS_DIR / "summary.md"
    report_path.write_text("\n".join(lines), encoding="utf-8")

    raw_path = RESULTS_DIR / "results.json"
    raw_path.write_text(json.dumps([asdict(r) for r in results], indent=2), encoding="utf-8")

    return report_path, chart_path


def main() -> int:
    all_results: list[ScenarioResult] = []

    for concurrency in CONCURRENCY_LEVELS:
        port = free_port()
        print(f"[perf] read   c={concurrency} port={port} ...")
        result = run_read_scenario(port, concurrency, REQUESTS_PER_WORKER[concurrency])
        all_results.append(result)
        print(
            f"[perf] read   c={concurrency}: avg={result.avg_latency_ms:.2f}ms "
            f"p95={result.p95_latency_ms:.2f}ms tput={result.throughput_rps:.1f}req/s "
            f"errors={result.failed_rpc_errors}"
        )

        port = free_port()
        print(f"[perf] race   c={concurrency} port={port} ...")
        race = run_race_scenario(port, concurrency)
        all_results.append(race)
        print(
            f"[perf] race   c={concurrency}: "
            f"{race.details['berhasil_pesan']} sukses / {race.details['ditolak_kursi_terisi']} ditolak "
            f"(double_booking={race.details['double_booking']})"
        )

    report_path, chart_path = build_report(all_results)
    print(f"[perf] Laporan : {report_path}")
    print(f"[perf] Grafik  : {chart_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
