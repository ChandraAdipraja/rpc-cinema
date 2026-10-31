# Cinema RPC — Reservasi Tiket Bioskop Terdistribusi

Mini-project RPC: sistem reservasi tiket bioskop yang **aman dari tabrakan booking**. Frontend React
berkomunikasi lewat FastAPI Gateway ke gRPC Server. Dua penonton (walau dari dua komputer berbeda) yang memilih
kursi sama dalam waktu bersamaan → hanya satu yang berhasil, sisanya otomatis ditolak dengan konflik `409` —
tanpa partial booking (multi-kursi direservasi all-or-nothing).

## Arsitektur

```
┌─────────────────────── Komputer 1 ───────────────────────┐        ┌──────── Komputer 2 ────────┐
│                                                          │        │                            │
│  ┌──────────┐   HTTP/SSE :8000   ┌────────────┐   gRPC   │◀──────►│  Frontend (Vite dev :5173) │
│  │ gRPC     │◀────────────────  │ FastAPI    │  :50051  │        │  └─ Browser demo           │
│  │ Server   │                   │ Gateway    │          │        │                            │
│  │ (state)  │                   │ (stateless)│          │        └────────────────────────────┘
│  └──────────┘                   └────────────┘          │
└──────────────────────────────────────────────────────────┘
```

- **gRPC Server** (`grpc_server/`) — single source of truth. Semua business logic: denah kursi **per jadwal**
  (film + jam), reservasi multi-kursi **all-or-nothing**, locking + idempotency `(op, request_id)`, dan
  **server streaming per jadwal** (`StreamStatusKursi`) dengan version counter per jadwal.
- **FastAPI Gateway** (`gateway/`) — jembatan HTTP ↔ gRPC + SSE. Stateless; error gRPC dipetakan ke HTTP
  (`400` invalid, `404` not found, `409` kursi sudah dipesan, `502` server tidak terjangkau).
- **Frontend React + TS + Vite + Tailwind** (`frontend/`) — 3 halaman utama: Beranda
  (Sedang Tayang / Segera Tayang / Promo & Voucher), Booking (pilih jam → denah multi-select kursi, real-time),
  detail Reservasi, plus **Tiket Saya** (`/tiket-saya`).

## Fitur

- **Jadwal dari server** — 4 film × 3 jam = 12 jadwal (RPC `LihatDaftarJadwal`).
- **Reservasi multi-kursi all-or-nothing** — pilih beberapa kursi sekaligus; gagal satu kursi = seluruh reservasi dibatalkan server.
- **Idempotency** — `request_id` per operasi logis: retry jaringan aman, hasil ter-cache (sukses/gagal).
- **Real-time per jadwal** — status kursi disiarkan via gRPC streaming + SSE; subscriber satu jadwal tidak diganggu mutasi jadwal lain.
- **Tiket Saya** — daftar tiket per perangkat (localStorage); tiket yang hilang karena server restart dilabeli "hilang".
- **Aman lintas mesin** — client dari dua komputer menuju satu server: race 1 pemenang, no double booking

## Struktur Repo

```
cinema-rpc/
├── AGENT.MD                  # spesifikasi project (sumber keputusan desain)
├── grpc_server/              # server gRPC + business logic
│   ├── proto/cinema.proto    # kontrak RPC (sumber kode yang digenerate)
│   ├── core/                 # storage (per jadwal), locking, idempotency
│   ├── services/             # implementasi RPC
│   ├── generated/            # stubs hasil generate (di .gitignore)
│   ├── cinema_client.py      # client demo: retry + timeout + backoff
│   ├── requirements.txt
│   └── server.py             # entry point gRPC server
├── gateway/                  # FastAPI gateway (HTTP/SSE ↔ gRPC)
│   ├── app/{routers, services, grpc_client, schemas}/
│   └── requirements.txt
├── frontend/                 # React + TS + Vite + Tailwind
│   ├── src/{pages, hooks, services, components}
│   └── .env.example
├── tests/                    # pytest: booking, concurrency, retry, streaming, gateway (36 test)
├── load_test/                # perf test + locust; hasil di results/
└── scripts/generate_proto.*  # regenerasi stubs proto
```

## Prasyarat

| Alat | Versi | Untuk |
|---|---|---|
| Python | ≥ 3.10 | server, gateway, test, perf test |
| Node.js + npm | ≥ 18 | frontend |

> Semua perintah di bawah ditulis untuk **Windows PowerShell** dari **root repo**. Path repo mengandung spasi — selalu pakai tanda kutip bila perlu.

## 1. Setup Awal (sekali saja)

### Backend Python

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r grpc_server\requirements.txt -r gateway\requirements.txt -r load_test\requirements.txt httpx
```

(Satu venv dipakai bersama server + gateway + test + perf test. `httpx` untuk test gateway.)

### Frontend

```powershell
cd frontend
npm install
cd ..
```

### Regenerasi stubs proto (wajib setelah clone, karena folder `generated/` tidak ikut git)

```powershell
cmd /c scripts\generate_proto.bat
```

## 2. Jalankan di Satu Komputer (3 terminal, dari root)

**Terminal 1 — gRPC server**

```powershell
.venv\Scripts\python.exe grpc_server\server.py
```

→ `[server] Cinema gRPC Server berjalan di port 50051 (12 jadwal aktif ...)`

**Terminal 2 — FastAPI gateway**

```powershell
.venv\Scripts\python.exe -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000
```

**Terminal 3 — frontend dev server**

```powershell
cmd /c "cd frontend && npm run dev"
```

**Buka:** `http://localhost:5173` — alur: pilih film & jam di Beranda → denah kursi → pilih → Reservasi.

### Versi produksi frontend (opsional)

```powershell
cmd /c "cd frontend && npm run build"
# hasil statis di frontend/dist — serve dengan cara apa pun,
# tapi lihat catatan CORS bila diakses dari origin selain localhost:5173
```

## 3. Jalankan di Dua Komputer

Topologi paling praktis:

- **Komputer A** (ada Python + repo penuh): gRPC server + gateway.
- **Komputer B** (cukup Node.js + folder `frontend/`; **tidak perlu Python**): frontend dev + browser demo.

**A. Di Komputer A — cari IP lokal:**

```powershell
ipconfig   # catat IPv4 Address, contoh: 192.168.1.10
```

**B. Di Komputer A — server + gateway (2 terminal):**

```powershell
.venv\Scripts\python.exe grpc_server\server.py
.venv\Scripts\python.exe -m uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000
```

Saat Windows Firewall tanya → **Allow access** (jaringan privat). Ini penyebab gagal #1.

**C. Di Komputer B — frontend (di folder `frontend/`):**

```bat
set VITE_API_URL=http://<IP-A>:8000
npm run dev -- --host 0.0.0.0
```

(`VITE_API_URL` menunjuk gateway di komputer A. Di PowerShell: `$env:VITE_API_URL="..."`.)

**D. Verifikasi sebelum demo** — dari komputer B, buka `http://<IP-A>:8000/api/health` → harus `{"status":"ok",...}`. Lalu buka `http://localhost:5173` di browser B.

**E. Demo andalan:** komputer A & B buka jadwal yang sama, pilih kursi sama, tekan pesan bersamaan → tepat satu sukses, satu `409`. Denah di kedua layar update real-time (SSE).

### Topologi alternatif (frontend dihost di A, dibuka browser dari B)

Browser B membuka `http://<IP-A>:5173` → origin browser bukan `localhost` → set CORS di gateway A:

```powershell
$env:CORS_ORIGINS = "http://<IP-A>:5173"
.venv\Scripts\python.exe -m uvicorn gateway.app.main:app --host 0.0.0.0 --port 8000
```

Dan jalankan Vite dengan `npm run dev -- --host 0.0.0.0`.

### Jebakan umum (2 mesin)

1. **JANGAN jalankan gRPC server di dua komputer.** State kursi in-memory → dua server = dua denah berbeda (split-brain). Semua mesin menunjuk SATU server.
2. **Tiket Saya = per perangkat** (localStorage). Tiket yang dipesan di komputer A tidak muncul di komputer B — ini desain, jelaskan saat demo.
3. WiFi kampus kadang mengisolasi antar-klien → health check gagal padahal config benar. Solusi: hotspot HP.
4. Data hilang saat server di-restart (in-memory). Tiket di "Tiket Saya" akan dilabeli "hilang".

## Variabel Environment

| Variabel | Dipakai di | Default | Arti |
|---|---|---|---|
| `GRPC_PORT` | server | `50051` | Port dengar gRPC server |
| `GRPC_TARGET` | gateway | `localhost:50051` | Alamat gRPC server yang dituju |
| `CORS_ORIGINS` | gateway | `http://localhost:5173,http://127.0.0.1:5173` | Origin frontend yang diizinkan (dipisah koma) |
| `VITE_API_URL` | frontend | `http://localhost:8000` | Alamat gateway dari browser |

## API Gateway (HTTP)

| Method | Path | Body/Query | Keterangan |
|---|---|---|---|
| GET | `/api/health` | — | Cek hidup |
| GET | `/api/jadwal` | — | Daftar 12 jadwal (film + jam) |
| GET | `/api/kursi` | `?schedule_id=` | Denah kursi satu jadwal |
| POST | `/api/pesan` | `{"schedule_id": "...", "seat_ids": ["A1","A2"]}` | Reservasi all-or-nothing; `409` bila ada kursi diambil |
| GET | `/api/pesanan/{reservation_id}` | — | Detail reservasi |
| POST | `/api/batal` | `{"reservation_id": "..."}` | Batalkan → semua kursi dibebaskan |
| GET | `/api/stream/kursi` | `?schedule_id=` | SSE real-time (server streaming per jadwal) |

Docs interaktif: `http://localhost:8000/docs`.

## RPC gRPC (`proto/cinema.proto`)

`LihatDaftarJadwal`, `LihatDaftarKursi`, `PesanKursi` (multi-seat + `request_id`), `BatalkanPesanan`,
`LihatDetailPesanan`, `StreamStatusKursi` (server streaming per jadwal).

Demo tanpa gateway:

```powershell
.venv\Scripts\python.exe grpc_server\cinema_client.py
```

## Testing

```powershell
# Full suite (booking, concurrency, retry, streaming, gateway) — 36 test
.venv\Scripts\python.exe -m pytest tests -v

# Perf test: skenario read c=1/5/20 + race booking; tulis hasil ke load_test/results/
.venv\Scripts\python.exe load_test\perf_test.py
```

Hasil perf ditulis ke `load_test/results/summary.md` + `chart.png`. Ringkasannya:

- read: 2.3k → 4.2k req/s (c=1→5), p95 kecil, 0 error;
- race booking di 1/5/20 client konkuren: **selalu tepat 1 pemenang, `double_booking=0`**.
- locust UI opsional: `.venv\Scripts\python.exe -m locust -f load_test\locustfile.py` (dengan server+gateway jalan).

## Catatan Desain

- **All-or-nothing**: server cek & kunci semua kursi dalam satu critical section — tidak pernah ada reservasi setengah jalan.
- **Idempotency `(op, request_id)`**: request ulang dengan `request_id` sama membalas hasil pertama (termasuk hasil GAGAL) tanpa efek samping berulang.
- **Locking**: satu `RLock` di seluruh state (scope mini-project, benar & sederhana).
- **Streaming per jadwal**: version counter per `schedule_id`; skip-wait hanya membangunkan subscriber jadwal yang berubah.
- **My Ticket**: `localStorage` (`cinema-rpc:my-ticket-ids`) — riwayat reservasi TIDAK dibuat di server (server restart = data hilang).