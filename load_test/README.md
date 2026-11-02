# Load Test Cinema RPC

Performa diukur melalui dua jalur yang terpisah dari demonstrasi UI:

| Alat | Target | File | Kegunaan |
|---|---|---|---|
| **Concurrent Python clients** (utama) | **gRPC Server langsung** | `perf_test.py` | Mengukur RPC murni: latensi, throughput, dan konsistensi race booking |
| **Race dua device** (demo) | **gRPC Server di komputer A** | `race_two_devices.py` | Membuktikan dua mesin yang mencoba kursi sama tetap tepat 1 pemenang |
| **Locust** (alternatif) | FastAPI Gateway (HTTP) | `locustfile.py` | Mengukur stack penuh HTTP → gRPC, dari sudut pandang client web |

## 1. Perf test utama — `perf_test.py`

```powershell
.venv\Scripts\python.exe load_test\perf_test.py
```

Skrip otomatis:
1. untuk setiap level concurrency `1, 5, 20` menyalakan **gRPC server baru** (port dinamis, state selalu fresh, tidak campur data run lain),
2. menjalankan skenario `read` (LihatDaftarKursi berulang: 200/500/1000 request) dan `race` (10 ronde per level; tiap ronde server baru + kursi bergiliran `A1..B3`, semua client lomba kursi yang sama lewat barrier),
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

## 2. Race dua device — `race_two_devices.py`

Khusus demo lintas mesin: membuktikan bahwa dua komputer yang menembak kursi
yang sama pada waktu hampir bersamaan tetap menghasilkan **tepat satu pemenang**
(`double booking = 0`). Skrip ini **tidak** menyalakan server; server gRPC
tetap hanya berjalan di komputer A.

Prasyarat:

- server gRPC hidup di komputer A dan port `50051` terbuka di firewall;
- kursi target masih bebas (skrip melakukan preflight dan berhenti jika terisi);
- jam kedua mesin sinkron. Di Windows (PowerShell admin): `w32tm /resync`.
  Di Linux: `sudo timedatectl set-ntp true` atau sinkronkan NTP.
  "Serempak" di sini berarti selisih **puluhan milidetik**, bukan mikrodetik —
  cukup untuk membuktikan tidak ada double booking.

Jalankan skrip yang sama di kedua mesin, dengan `--seat`, `--rounds`, dan
`--start-at` yang sama:

```powershell
# Komputer A (server)
$env:GRPC_TARGET="localhost:50051"
python load_test\race_two_devices.py --label A --seat A1 --rounds 6 --start-at 20:15:00

# Komputer B (client)
$env:GRPC_TARGET="<IP-A>:50051"
python load_test\race_two_devices.py --label B --seat A1 --rounds 6 --start-at 20:15:00
```

`--seat` adalah **kursi awal** urutan ronde: `A1,A2,A3,B1,B2,B3` lalu berputar
kembali ke awal bila `--rounds > 6` (kursi yang sudah terpakai akan konflik).
`--start-at` hanya mengatur tembakan **ronde pertama**; ronde berikutnya
langsung menyusul. Tanpa `--start-at` skrip langsung menembak.

Contoh output:

```text
[race] label=A target=localhost:50051 schedule=m-gerhana-1030 rounds=6 seats=A1,A2,A3,B1,B2,B3
[race] menunggu 20:15:00 ...
[race] A 20:15:00.012 A1 MENANG 12.3ms
[race] A 20:15:00.145 A2 KONFLIK 9.8ms
...
[race] ringkasan label=A: ronde=6 menang=3 konflik=3 error=0 avg=11.2ms
[race] JSON: ...\load_test\results\race_A_20261102_201500.json
```

Cara membaca hasil:

- gabungkan JSON dari A dan B; untuk **setiap kursi** jumlah `MENANG` dari
  kedua mesin harus **tepat 1**;
- total `MENANG` A + B harus sama dengan jumlah ronde, dan `double booking = 0`;
- `KONFLIK` adalah hasil yang benar (server menolak), bukan kegagalan;
- `ERROR <kode>` berarti masalah jaringan/server dan tidak membuktikan apa pun.

Kursi yang menang tetap terpesan setelah skrip selesai. Restart server gRPC
untuk mengulang demo dari state bersih.

## 3. Locust — `locustfile.py`

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
- **Race consistency**: pada setiap ronde, hasil yang BENAR adalah tepat 1 client
  berhasil memesan, sisanya ditolak dengan pesan "kursi sudah dipesan", dan
  `double_booking = 0`. Total pemenang per level harus sama dengan jumlah ronde.
