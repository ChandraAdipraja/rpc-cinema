# Hasil Performance Test Cinema RPC

Dihasilkan otomatis oleh `perf_test.py` pada 2026-11-02 16:02:02.

## Konfigurasi pengujian

- Interpreter: Python 3.14.7 (`Windows-11-10.0.26300-SP0`)
- Target langsung: gRPC Server (belum melalui FastAPI Gateway).
- Skenario `read`: 1 client = 1 THREAD = 1 koneksi gRPC; tanpa think-time;
  jumlah request per level: 1 client x 200, 5 client x 100, 20 client x 50 req.
- Skenario `race`: seluruh client memanggil PesanKursi kursi A1 serentak (barrier);
  tiap client lakukan warmup koneksi 1x LihatDaftarKursi sebelum barrier agar yang
  terukur hanya latensi booking, bukan DNS/TCP setup.
- Server: 1 instance gRPC baru per skenario (state in-memory selalu fresh),
  ThreadPoolExecutor 32 worker, port dinamis.
- Latensi diukur dengan `time.perf_counter()` per panggilan RPC; warmup 10 call
  per client diabaikan sebelum pengukuran.

**Catatan (berlaku jika pakai Locust):** jumlah virtual users Locust *tidak* otomatis
sama dengan koneksi aktif yang sedang mati — Locust memanajemen spawn-rate dan
wait-time, sehingga update konfigurasi harus dijelaskan di ini (jarak antara user,
think-time, dan apakah endpoint-nya HTTP/gRPC). Skrip utama di repo ini menghindari
ambigu karena 1 worker memang tepat 1 koneksi.

## Tabel hasil skenario `read` (LihatDaftarKursi)

| Jenis | Client | Total Req | RPC Error | Avg (ms) | P95 (ms) | Throughput (req/s) | Success Rate |
|---|---|---|---|---|---|---|---|
| read | 1 | 200 | 0 | 0.72 | 1.02 | 1297.8 | 100.0% |
| read | 5 | 500 | 0 | 2.05 | 2.88 | 2136.7 | 100.0% |
| read | 20 | 1000 | 0 | 8.19 | 10.16 | 1919.2 | 100.0% |

## Tabel hasil skenario `race` (PesanKursi, kursi sama)

| Jenis | Client | Total Attempt | RPC Error | Avg (ms) | P95 (ms) | Latensi terlama (ms) | Success Rate* |
|---|---|---|---|---|---|---|---|
| race | 1 | 1 | 0 | 4.27 | 4.27 | 4.27 | 100.0% |
| race | 5 | 5 | 0 | 2.71 | 3.47 | 3.33 | 100.0% |
| race | 20 | 20 | 0 | 5.88 | 9.24 | 9.24 | 100.0% |

\* Race test: "success rate" 100% berarti SEMUA attempt mendapat response valid
(1 yang berhasil memesan, sisanya ditolak server karena kursi sudah terisi —
ini perilaku yang BENAR). "Latensi terlama" = attempt paling lambat di antara
seluruh client pada level tersebut (biasanya pemenang kursi). Rincian per level:
- 1 client: 1 berhasil, 0 ditolak, 0 RPC error, double booking = 0
- 5 client: 1 berhasil, 4 ditolak, 0 RPC error, double booking = 0
- 20 client: 1 berhasil, 19 ditolak, 0 RPC error, double booking = 0