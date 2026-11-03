"""Uji toleransi kegagalan: timeout, retry, backoff, dan idempotensi.

Skenario 'down'   : server MATI -> client mencoba 3 kali lalu gagal.
Skenario 'recover': server MATI saat dipanggil, lalu DINYALAKAN kembali
                    sebelum retry habis -> pemanggilan akhirnya berhasil.

Contoh:
  python load_test/failure_test.py down --target localhost:50051
  python load_test/failure_test.py recover --target <IP-A>:50051
"""
from __future__ import annotations

import argparse
import sys
import time
import uuid
from pathlib import Path

import grpc

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "grpc_server"))

import cinema_client  # noqa: E402
from cinema_client import CinemaRpcClient  # noqa: E402
from stubs import cinema_pb2  # noqa: E402

T0 = time.perf_counter()


def log(msg: str) -> None:
    print(f"[{time.perf_counter() - T0:6.2f}s] {msg}", flush=True)


# Cetak setiap backoff agar kejadian retry terlihat di log.
_real_sleep = time.sleep
_attempt = {"n": 0}


def _logged_sleep(seconds: float) -> None:
    _attempt["n"] += 1
    log(f"  retry #{_attempt['n']}: gagal, menunggu backoff {seconds:.1f} detik")
    _real_sleep(seconds)


cinema_client.time.sleep = _logged_sleep


def skenario_down(target: str) -> int:
    client = CinemaRpcClient(target=target)  # timeout 3 s, retry 2x, backoff 0,5 s
    log(f"Memanggil LihatDaftarJadwal ke {target} (server mati)...")
    try:
        client.lihat_daftar_jadwal()
    except grpc.RpcError as err:
        log(f"GAGAL setelah {_attempt['n']} kali retry: {err.code().name}")
        return 0
    finally:
        client.close()
    log("Tidak ada error (server ternyata hidup).")
    return 1


def skenario_recover(target: str) -> int:
    # Retry diperbanyak agar ada waktu ~30 detik untuk menyalakan server lagi.
    client = CinemaRpcClient(target=target, timeout=3.0, max_retries=6, backoff_base=0.5)
    try:
        log("Mengambil jadwal dan kursi (server HARUS hidup dulu)...")
        jadwal = client.lihat_daftar_jadwal().daftar_jadwal[0]
        kursi = [k.id for k in client.lihat_daftar_kursi(jadwal.schedule_id).daftar_kursi
                 if k.status == cinema_pb2.KURSI_AVAILABLE][:1]
        input(">>> MATIKAN server sekarang (Ctrl+C di jendela server), lalu tekan Enter...")
        request_id = str(uuid.uuid4())
        log(f">>> Memanggil PesanKursi {kursi} dengan request_id={request_id[:8]}...")
        log(">>> NYALAKAN server lagi dalam ~30 detik!")
        _attempt["n"] = 0
        hasil = client.pesan_kursi(request_id, jadwal.schedule_id, kursi)
        log(f"BERHASIL setelah {_attempt['n']} kali retry: success={hasil.success}")
        log(f"reservation_id={hasil.reservasi.reservation_id}")
        ulang = client.pesan_kursi(request_id, jadwal.schedule_id, kursi)
        sama = ulang.reservasi.reservation_id == hasil.reservasi.reservation_id
        log(f"Kirim ulang request_id sama -> reservation_id sama: {sama}")
        return 0
    except grpc.RpcError as err:
        log(f"GAGAL: {err.code().name} (server tidak sempat hidup)")
        return 1
    finally:
        client.close()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("skenario", choices=["down", "recover"])
    ap.add_argument("--target", default="localhost:50051")
    a = ap.parse_args()
    return skenario_down(a.target) if a.skenario == "down" else skenario_recover(a.target)


if __name__ == "__main__":
    sys.exit(main())