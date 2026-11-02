# Remote gRPC Performance Test

- Target          : `localhost:50073`
- Schedule        : `m-gerhana-1030`
- Waktu           : 2026-11-02 16:23:24
- Mesin penguji   : `DESKTOP-DNJ4J66` (Windows 11)
- Python          : 3.14.7
- Mode            : read-only `LihatDaftarKursi` (tanpa spawn server, tanpa booking)

## Hasil

| Concurrency | Requests | Errors | Avg (ms) | p95 (ms) | Throughput (req/s) | Success |
|---|---|---|---|---|---|---|
| 1 | 200 | 0 | 0.63 | 0.93 | 1590.3 | 100.0% |
| 5 | 500 | 0 | 1.83 | 2.49 | 2719.0 | 100.0% |
| 20 | 1000 | 0 | 8.89 | 15.86 | 2213.4 | 100.0% |

## Catatan

- Angka termasuk RTT jaringan (WiFi/LAN), bukan hanya biaya server.
- Throughput dibatasi mesin penguji + jaringan; bukan kapasitas maksimum server.
- Jalankan server dengan `LOG_LEVEL=WARNING` saat pengukuran agar log per-RPC tidak menjadi bottleneck.
- Tidak sebanding langsung dengan `perf_test.py` (lokal, server baru per skenario).
