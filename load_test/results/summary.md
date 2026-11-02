# Hasil Performance Test Cinema RPC

Dihasilkan otomatis oleh `perf_test.py` pada 2026-11-02 17:12:47.

## Konfigurasi pengujian

- Interpreter: Python 3.14.7 (`Windows-11-10.0.26300-SP0`)
- Target langsung: gRPC Server (belum melalui FastAPI Gateway).
- Skenario `read`: 1 client = 1 THREAD = 1 koneksi gRPC; tanpa think-time;
  jumlah request per level: 1 client x 200, 5 client x 100, 20 client x 50 req.
- Skenario `race`: 10 ronde per level; tiap ronde memakai server baru
  (state fresh) dan kursi bergiliran A1, A2, A3, B1, B2, B3 (berputar bila ronde > 6);
  seluruh client pada satu ronde memanggil PesanKursi untuk kursi yang sama serentak
  (barrier); tiap client lakukan warmup koneksi 1x LihatDaftarKursi sebelum barrier agar
  yang terukur hanya latensi booking, bukan DNS/TCP setup.
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
| read | 1 | 200 | 0 | 1.61 | 3.56 | 580.6 | 100.0% |
| read | 5 | 500 | 0 | 2.45 | 3.96 | 1785.8 | 100.0% |
| read | 20 | 1000 | 0 | 9.90 | 11.75 | 1617.4 | 100.0% |

## Tabel hasil skenario `race` (PesanKursi, kursi sama per ronde)

| Jenis | Client | Ronde | Total Attempt | Menang | Double Booking | RPC Error | Avg (ms) | P95 (ms) | Success Rate* |
|---|---|---|---|---|---|---|---|---|---|
| race | 1 | 10 | 10 | 10 | 0 | 0 | 1.43 | 2.30 | 100.0% |
| race | 5 | 10 | 50 | 10 | 0 | 0 | 3.27 | 9.47 | 100.0% |
| race | 20 | 10 | 200 | 10 | 0 | 0 | 5.37 | 8.67 | 100.0% |

\* Race test: "success rate" 100% berarti SEMUA attempt mendapat response valid
(tepat 1 yang berhasil memesan per ronde, sisanya ditolak server karena kursi sudah
terisi — ini perilaku yang BENAR). `Double Booking` harus 0; nilainya dihitung dari
kelebihan pemenang pada setiap ronde. Rincian per level:
- 1 client: 10 ronde, 10 menang, 0 ditolak, 0 RPC error, double booking = 0
- 5 client: 10 ronde, 10 menang, 40 ditolak, 0 RPC error, double booking = 0
- 20 client: 10 ronde, 10 menang, 190 ditolak, 0 RPC error, double booking = 0