# Hasil Performance Test Cinema RPC

Dihasilkan otomatis oleh `perf_test.py` pada 2026-10-31 16:20:51.

## Konfigurasi pengujian

- Interpreter: Python 3.10.10 (`Windows-10-10.0.26100-SP0`)
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
| read | 1 | 200 | 0 | 0.39 | 0.46 | 2335.6 | 100.0% |
| read | 5 | 500 | 0 | 1.03 | 1.20 | 4248.1 | 100.0% |
| read | 20 | 1000 | 0 | 4.05 | 4.38 | 3973.1 | 100.0% |

## Tabel hasil skenario `race` (PesanKursi, kursi sama)

| Jenis | Client | Total Attempt | RPC Error | Avg (ms) | P95 (ms) | Latensi terlama (ms) | Success Rate* |
|---|---|---|---|---|---|---|---|
| race | 1 | 1 | 0 | 0.55 | 0.55 | 0.55 | 100.0% |
| race | 5 | 5 | 0 | 0.86 | 1.26 | 1.14 | 100.0% |
| race | 20 | 20 | 0 | 2.20 | 3.04 | 3.04 | 100.0% |

\* Race test: "success rate" 100% berarti SEMUA attempt mendapat response valid
(1 yang berhasil memesan, sisanya ditolak server karena kursi sudah terisi —
ini perilaku yang BENAR). "Latensi terlama" = attempt paling lambat di antara
seluruh client pada level tersebut (biasanya pemenang kursi). Rincian per level:
- 1 client: 1 berhasil, 0 ditolak, 0 RPC error, double booking = 0
- 5 client: 1 berhasil, 4 ditolak, 0 RPC error, double booking = 0
- 20 client: 1 berhasil, 19 ditolak, 0 RPC error, double booking = 0