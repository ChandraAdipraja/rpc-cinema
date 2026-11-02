# Remote gRPC Performance Test

- Target          : `192.168.18.229:50051`
- Schedule        : `m-gerhana-1030`
- Waktu           : 2026-11-02 16:37:38
- Mesin penguji   : `DESKTOP-DNJ4J66` (Windows 11)
- Python          : 3.14.7
- Mode            : read-only `LihatDaftarKursi` (tanpa spawn server, tanpa booking)

## Hasil

| Concurrency | Requests | Errors | Avg (ms) | p95 (ms) | Throughput (req/s) | Success |
|---|---|---|---|---|---|---|
| 1 | 200 | 0 | 8.07 | 16.57 | 123.9 | 100.0% |
| 5 | 500 | 0 | 14.55 | 31.97 | 310.5 | 100.0% |
| 20 | 1000 | 0 | 38.72 | 76.25 | 511.7 | 100.0% |

## Catatan

- Angka termasuk RTT jaringan (WiFi/LAN), bukan hanya biaya server.
- Throughput dibatasi mesin penguji + jaringan; bukan kapasitas maksimum server.
- Jalankan server dengan `LOG_LEVEL=WARNING` saat pengukuran agar log per-RPC tidak menjadi bottleneck.
- Tidak sebanding langsung dengan `perf_test.py` (lokal, server baru per skenario).
