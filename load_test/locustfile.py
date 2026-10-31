"""Locustfile alternatif: load test FastAPI Gateway (HTTP) di depan gRPC server.

Skenario:
- 4 : GET  /api/kursi  (baca daftar kursi)
- 1 : POST /api/pesan + POST /api/batal (reservasi lalu langsung dibatalkan,
      agar state kembali stabil untuk iterasi berikutnya)

Yang terukur di sini adalah stack PENUH (HTTP -> FastAPI -> gRPC -> server),
bukan RPC murni. Untuk mengukur performa gRPC langsung gunakan perf_test.py.

Jalankan:
1. Hidupkan server & gateway (lihat README).
2. .venv/Scripts/python.exe -m locust -f load_test/locustfile.py
   - buka http://localhost:8089 lalu set users & spawn-rate.
   Atau headless: -m locust -f load_test/locustfile.py --headless
      -u 20 -r 5 -t 30s --host http://localhost:8000

CATATAN PENTING (sesuai permintaan soal):
Jumlah virtual users Locust TIDAK otomatis sama dengan jumlah koneksi yang
sedang aktif. Saat spawn (mis. 20 user, spawn-rate 5/s) butuh waktu ~4 detik
sampai SEMUA user benar-benar hidup, dan wait_time membuat tiap user tidak
selalu sedang memegang koneksi. Perlakukan angka "Users" Locust sebagai
PEMBERAT, bukan ukuran koneksi; gunakan grafik "Current RPS" + response time
di UI Locust, dan pastikan hasil dibandingkan dengan konfigurasi yang sama.
"""

import random

from locust import HttpUser, between, task

# Denah kursi Server: A1-A3, B1-B3 (default saat server dijalankan tanpa perubahan).
CANDIDATE_SEATS = ["A1", "A2", "A3", "B1", "B2", "B3"]


class CinemaHttpUser(HttpUser):
    wait_time = between(0.5, 1.5)

    @task(4)
    def lihat_daftar_kursi(self):
        self.client.get("/api/kursi", name="/api/kursi [read]")

    @task(1)
    def pesan_lalu_batal(self):
        seat = random.choice(CANDIDATE_SEATS)
        response = self.client.post(
            "/api/pesan",
            json={"seat_id": seat},
            name="/api/pesan [+batal]",
        )
        if response.status_code == 200:
            body = response.json()
            reservation_id = body["reservasi"]["reservation_id"]
            self.client.post(
                "/api/batal",
                json={"reservation_id": reservation_id},
                name="/api/batal [berkaitan]",
            )
        elif response.status_code == 409:
            # Kursi diambil orang lain -> perilaku bisnis yang benar, bukan error.
            response.success()
