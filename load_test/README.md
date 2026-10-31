# Load Test Cinema RPC

Performa diukur melalui dua jalur yang terpisah dari demonstrasi UI:

| Alat | Target | File | Kegunaan |
|---|---|---|---|
| **Concurrent Python clients** (utama) | **gRPC Server langsung** | `perf_test.py` | Mengukur RPC murni: latensi, throughput, dan konsistensi race booking |
| **Locust** (alternatif) | FastAPI Gateway (HTTP) | `locustfile.py` | Mengukur stack penuh HTTP → gRPC, dari sudut pandang client web |

## 1. Perf test utama — `perf_test.py`

```powershell
.venv\Scripts\python.exe load_test\perf_test.py
```

Skrip otomatis:
1. untuk setiap level concurrency `1, 5, 20` menyalakan **gRPC server baru** (port dinamis, state selalu fresh, tidak campur data run lain),
2. menjalankan skenario `read` (LihatDaftarKursi berulang: 200/500/1000 request) dan `race` (semua client lomba pesan kursi A1 sekaligus lewat barrier),
3. menulis hasil ke `results/`:
   - `summary.md` — tabel + penjelasan konfigurasi (bahan laporan),
   - `chart.png` — grafik throughput, latensi (avg & p95), dan hasil race,
   - `results.json` — data mentah bila ingin diolah ulang.

### Konfigurasi yang saat ini dipakai (wajib dilaporkan konsisten)
- 1 client = **1 thread = 1 koneksi gRPC** murni (tidak ada pooling).
- Tanpa think-time: beban maksimal berkelanjutan.
- Warmup 10 request per client diabaikan dari pengukuran.
- Latensi per panggilan diukur `time.perf_counter()`.
- Timeout client 5 s, retry read = 2x dengan backoff 0.2–0.4 s, race = tanpa retry.

### Penting soal Locust
Jumlah **virtual users** Locust *tidak* sama dengan jumlah koneksi yang
benar-benar aktif: spawn santai (rincian spawn-rate) dan `wait_time` membuat
user tidak selalu sedang mengirim request. Karena itu:
- Gunakan `perf_test.py` untuk angka laporan yang ketat (1:1 client↔koneksi).
- Jika memakai Locust, laporkan konfigurasi penuh (users, spawn-rate, wait_time,
  user_class) dan bandingkan hanya hasil dengan konfigurasi yang identik.

## 2. Locust — `locustfile.py`

```powershell
# Terminal 1
.venv\Scripts\python.exe grpc_server\server.py
# Terminal 2
.venv\Scripts\python.exe -m uvicorn gateway.app.main:app --port 8000
# Terminal 3 (dari ROOT repo)
.venv\Scripts\python.exe -m locust -f load_test\locustfile.py
# lalu buka http://localhost:8089 (host default: http://localhost:8000)

# atau headless:
.venv\Scripts\python.exe -m locust -f load_test\locustfile.py --headless -u 20 -r 5 -t 30s --host http://localhost:8000
```

Skenario Locust: 4× `GET /api/kursi` dan 1× `POST /api/pesan` + `POST /api/batal`
(reservasi langsung dibatalkan agar state stabil). Response **409** dianggap
sukses logis — persaingan kursi adalah perilaku bisnis yang benar.

## Kriteria kualitas yang diukur

- **Latency**: avg & p95 per RPC.
- **Throughput**: request/detik.
- **Total & failed requests**: termasuk error RPC (timeout/unavailable).
- **Race consistency**: pada setiap level concurrency, hasil yang BENAR adalah
  tepat 1 client berhasil memesan, sisanya ditolak dengan pesan "kursi sudah
  dipesan", dan `double_booking = 0`.
