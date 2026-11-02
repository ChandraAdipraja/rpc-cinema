"""Uji latensi & throughput gRPC ke server yang SUDAH berjalan (mis. device 1).

Berbeda dari `perf_test.py`:
- tidak men-spawn server sendiri; target ditentukan lewat `--target` / `GRPC_TARGET`;
- read-only (hanya `LihatDaftarJadwal` + `LihatDaftarKursi`), jadi state server
  tidak berubah dan aman dijalankan saat demo;
- tidak butuh matplotlib untuk menulis laporan; grafik dilewati bila belum terpasang.

Jalankan dari root repo:

    python load_test/remote_perf_test.py --target 192.168.18.229:50051

Hasil ditulis ke `load_test/results/`:
- `remote_summary.md`  : tabel + catatan konfigurasi
- `remote_results.json`: data mentah
- `remote_chart.png`   : grafik throughput & latensi

Angka yang diukur termasuk RTT jaringan, jadi hanya bandingkan dengan
konfigurasi yang sama (target, WiFi, dan beban mesin). Saat mengukur, jalankan
server dengan `LOG_LEVEL=WARNING` agar penulisan log per-RPC tidak menjadi
bottleneck.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "grpc_server") not in sys.path:
    sys.path.insert(0, str(ROOT / "grpc_server"))

import grpc

from cinema_client import CinemaRpcClient

CONCURRENCY_LEVELS = [1, 5, 20]
REQUESTS_PER_WORKER = {1: 200, 5: 100, 20: 50}
WARMUP_REQUESTS = 10
READY_TIMEOUT_S = 10.0
DEFAULT_TIMEOUT_S = 5.0
RESULTS_DIR = Path(__file__).resolve().parent / "results"


@dataclass
class LevelResult:
    concurrency: int
    total_requests: int
    failed_rpc_errors: int
    elapsed_seconds: float
    avg_latency_ms: float
    p95_latency_ms: float
    throughput_rps: float
    success_rate_pct: float
    error_codes: list[str]


def _p95(latencies: list[float]) -> float:
    if len(latencies) < 2:
        return latencies[0] if latencies else 0.0
    return statistics.quantiles(latencies, n=20)[18]


def _normalize_target(raw: str) -> str:
    target = raw.strip()
    for prefix in ("http://", "https://", "grpc://"):
        if target.startswith(prefix):
            target = target[len(prefix) :]
    return target.rstrip("/")


def _wait_ready(client: CinemaRpcClient) -> str:
    """Tunggu server menjawab; kembalikan schedule_id pertama."""
    deadline = time.monotonic() + READY_TIMEOUT_S
    last_error: str = "-"
    while time.monotonic() < deadline:
        try:
            jadwal = client.lihat_daftar_jadwal()
        except grpc.RpcError as err:
            last_error = err.code().name
            time.sleep(0.3)
            continue
        if not jadwal.daftar_jadwal:
            raise RuntimeError("server menjawab tetapi daftar jadwal kosong")
        return jadwal.daftar_jadwal[0].schedule_id
    raise RuntimeError(
        f"server tidak menjawab dalam {READY_TIMEOUT_S:.0f}s (error terakhir: {last_error})"
    )


def run_level(
    target: str, schedule_id: str, concurrency: int, requests_each: int, timeout: float
) -> LevelResult:
    latencies: list[float] = []
    errors: list[str] = []
    windows: list[tuple[float, float]] = []
    lock = threading.Lock()
    barrier = threading.Barrier(concurrency)

    def worker(_: int) -> None:
        client = CinemaRpcClient(target=target, timeout=timeout, max_retries=0)
        try:
            for _ in range(WARMUP_REQUESTS):
                client.lihat_daftar_kursi(schedule_id)

            # Semua worker mulai fase terukur bersamaan.
            barrier.wait(timeout=READY_TIMEOUT_S)
            started = time.perf_counter()
            local_latencies: list[float] = []
            local_errors: list[str] = []
            for _ in range(requests_each):
                call_start = time.perf_counter()
                try:
                    client.lihat_daftar_kursi(schedule_id)
                except grpc.RpcError as err:
                    local_errors.append(err.code().name)
                finally:
                    local_latencies.append((time.perf_counter() - call_start) * 1000.0)
            finished = time.perf_counter()

            with lock:
                latencies.extend(local_latencies)
                errors.extend(local_errors)
                windows.append((started, finished))
        finally:
            client.close()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        list(pool.map(worker, range(concurrency)))

    if not latencies or not windows:
        raise RuntimeError(f"tidak ada request terukur pada concurrency={concurrency}")

    # Wall time fase terukur: dari worker paling awal mulai sampai paling akhir selesai.
    elapsed = max(end for _, end in windows) - min(start for start, _ in windows)
    total = len(latencies)
    return LevelResult(
        concurrency=concurrency,
        total_requests=total,
        failed_rpc_errors=len(errors),
        elapsed_seconds=elapsed,
        avg_latency_ms=statistics.mean(latencies),
        p95_latency_ms=_p95(latencies),
        throughput_rps=total / elapsed if elapsed > 0 else 0.0,
        success_rate_pct=100.0 * (total - len(errors)) / total,
        error_codes=sorted(set(errors)),
    )


def _build_chart(results: list[LevelResult], path: Path) -> bool:
    try:
        import matplotlib
    except ImportError:
        print(
            "[remote] matplotlib tidak terpasang; grafik dilewati. "
            "Install: python -m pip install -r load_test/requirements.txt"
        )
        return False

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    levels = [str(r.concurrency) for r in results]

    fig, (ax1, ax2, ax3) = plt.subplots(1, 3, figsize=(16, 4.8))
    fig.suptitle("Remote gRPC Read Test (LihatDaftarKursi)", fontsize=12)

    ax1.bar(levels, [r.throughput_rps for r in results], color="#f59e0b")
    ax1.set_title("Throughput")
    ax1.set_xlabel("Concurrent clients")
    ax1.set_ylabel("req/s")
    for i, result in enumerate(results):
        ax1.text(
            i, result.throughput_rps, f"{result.throughput_rps:.0f}",
            ha="center", va="bottom", fontsize=9,
        )

    ax2.plot(levels, [r.avg_latency_ms for r in results], "o-", color="#10b981", label="avg")
    ax2.plot(levels, [r.p95_latency_ms for r in results], "s--", color="#ef4444", label="p95")
    ax2.set_title("Latency")
    ax2.set_xlabel("Concurrent clients")
    ax2.set_ylabel("ms")
    ax2.legend()

    rates = [r.success_rate_pct for r in results]
    ax3.bar(levels, rates, color="#10b981")
    ax3.set_title("Success rate")
    ax3.set_xlabel("Concurrent clients")
    ax3.set_ylabel("%")
    ax3.set_ylim(0, 105)
    for i, result in enumerate(results):
        label = f"{result.success_rate_pct:.1f}%"
        if result.failed_rpc_errors:
            label += f" ({result.failed_rpc_errors} err)"
        ax3.text(i, result.success_rate_pct, label, ha="center", va="bottom", fontsize=8)

    fig.tight_layout()
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return True


def write_reports(
    target: str, schedule_id: str, results: list[LevelResult], started_at: datetime
) -> tuple[Path, Path, Path | None]:
    RESULTS_DIR.mkdir(exist_ok=True)

    summary_path = RESULTS_DIR / "remote_summary.md"
    json_path = RESULTS_DIR / "remote_results.json"
    chart_path = RESULTS_DIR / "remote_chart.png"

    baris = [
        "| Concurrency | Requests | Errors | Avg (ms) | p95 (ms) | Throughput (req/s) | Success |",
        "|---|---|---|---|---|---|---|",
    ]
    for result in results:
        baris.append(
            f"| {result.concurrency} | {result.total_requests} | {result.failed_rpc_errors} | "
            f"{result.avg_latency_ms:.2f} | {result.p95_latency_ms:.2f} | "
            f"{result.throughput_rps:.1f} | {result.success_rate_pct:.1f}% |"
        )

    summary = "\n".join(
        [
            "# Remote gRPC Performance Test",
            "",
            f"- Target          : `{target}`",
            f"- Schedule        : `{schedule_id}`",
            f"- Waktu           : {started_at.strftime('%Y-%m-%d %H:%M:%S')}",
            f"- Mesin penguji   : `{platform.node()}` ({platform.system()} {platform.release()})",
            f"- Python          : {platform.python_version()}",
            "- Mode            : read-only `LihatDaftarKursi` (tanpa spawn server, tanpa booking)",
            "",
            "## Hasil",
            "",
            *baris,
            "",
            "## Catatan",
            "",
            "- Angka termasuk RTT jaringan (WiFi/LAN), bukan hanya biaya server.",
            "- Throughput dibatasi mesin penguji + jaringan; bukan kapasitas maksimum server.",
            "- Jalankan server dengan `LOG_LEVEL=WARNING` saat pengukuran agar log per-RPC tidak menjadi bottleneck.",
            "- Tidak sebanding langsung dengan `perf_test.py` (lokal, server baru per skenario).",
            "",
        ]
    )
    summary_path.write_text(summary, encoding="utf-8")

    payload = {
        "target": target,
        "schedule_id": schedule_id,
        "timestamp": started_at.isoformat(timespec="seconds"),
        "host": platform.node(),
        "platform": f"{platform.system()} {platform.release()}",
        "python": platform.python_version(),
        "levels": [asdict(result) for result in results],
    }
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    chart_written = _build_chart(results, chart_path)
    return summary_path, json_path, chart_path if chart_written else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Ukur latensi & throughput gRPC ke server yang sudah berjalan."
    )
    parser.add_argument(
        "--target",
        default=os.getenv("GRPC_TARGET", "localhost:50051"),
        help="host:port server gRPC (default: GRPC_TARGET atau localhost:50051)",
    )
    parser.add_argument(
        "--timeout", type=float, default=DEFAULT_TIMEOUT_S, help="deadline per RPC (detik)"
    )
    args = parser.parse_args(argv)
    target = _normalize_target(args.target)
    if not target:
        print("[remote] target kosong; isi --target atau GRPC_TARGET")
        return 2

    print(f"[remote] target={target}")
    print(f"[remote] mode=read-only, konkurensi={CONCURRENCY_LEVELS}")
    print("[remote] pastikan server memakai LOG_LEVEL=WARNING saat pengukuran")

    readiness = CinemaRpcClient(
        target=target, timeout=args.timeout, max_retries=2, backoff_base=0.2
    )
    try:
        schedule_id = _wait_ready(readiness)
    except RuntimeError as err:
        print(f"[remote] GAGAL: {err}")
        print(
            "[remote] Periksa: server hidup, IP/port benar, satu jaringan, dan "
            "firewall inbound TCP 50051 terbuka di device server."
        )
        return 1
    finally:
        readiness.close()

    print(f"[remote] schedule={schedule_id}")

    results: list[LevelResult] = []
    for concurrency in CONCURRENCY_LEVELS:
        requests_each = REQUESTS_PER_WORKER[concurrency]
        print(f"[remote] c={concurrency} requests/client={requests_each} ...")
        try:
            result = run_level(
                target, schedule_id, concurrency, requests_each, args.timeout
            )
        except (RuntimeError, grpc.RpcError, threading.BrokenBarrierError) as err:
            print(f"[remote] GAGAL pada c={concurrency}: {err}")
            return 1
        results.append(result)
        print(
            f"[remote] c={concurrency:<2} total={result.total_requests} "
            f"avg={result.avg_latency_ms:.2f}ms p95={result.p95_latency_ms:.2f}ms "
            f"tput={result.throughput_rps:.1f}req/s errors={result.failed_rpc_errors}"
        )

    summary_path, json_path, chart_path = write_reports(
        target, schedule_id, results, datetime.now()
    )
    print(f"[remote] Laporan: {summary_path}")
    print(f"[remote] JSON   : {json_path}")
    if chart_path is not None:
        print(f"[remote] Grafik : {chart_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
