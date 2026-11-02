"""Uji logika race_two_devices dengan dua label terhadap server lokal."""

from __future__ import annotations

import json
import sys
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "load_test") not in sys.path:
    sys.path.insert(0, str(ROOT / "load_test"))

import race_two_devices as race
from cinema_client import CinemaRpcClient
from stubs import cinema_pb2


def _first_free_seat(client: CinemaRpcClient, schedule_id: str) -> str:
    daftar = client.lihat_daftar_kursi(schedule_id)
    return next(
        kursi.id
        for kursi in daftar.daftar_kursi
        if kursi.status == cinema_pb2.KURSI_AVAILABLE
    )


def test_dua_label_tepat_satu_pemenang_per_kursi(server, tmp_path):
    # Urutan kursi dimulai dari --seat lalu berputar.
    assert race.seat_sequence("B2", 4) == ["B2", "B3", "A1", "A2"]

    target = f"localhost:{server.port}"
    schedule_id = server.client.lihat_daftar_jadwal().daftar_jadwal[0].schedule_id
    seat = _first_free_seat(server.client, schedule_id)

    clients = {
        label: CinemaRpcClient(target=target, timeout=5.0, max_retries=0)
        for label in ("A", "B")
    }
    barrier = threading.Barrier(2)
    results: dict[str, race.RoundResult] = {}
    errors: list[BaseException] = []

    def worker(label: str) -> None:
        try:
            barrier.wait(timeout=5)
            results[label] = race.fire_round(clients[label], schedule_id, seat, label, 1)
        except BaseException as err:  # noqa: BLE001 - dikirim ulang ke thread utama
            errors.append(err)
        finally:
            clients[label].close()

    threads = [threading.Thread(target=worker, args=(label,)) for label in ("A", "B")]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)

    assert not errors, errors
    assert set(results) == {"A", "B"}
    assert sorted(result.outcome for result in results.values()) == [
        race.KONFLIK,
        race.MENANG,
    ]
    assert {result.seat for result in results.values()} == {seat}

    summary = race.summarize(list(results.values()))
    assert summary == {
        "rounds": 2,
        "menang": 1,
        "konflik": 1,
        "error": 0,
        "avg_latency_ms": summary["avg_latency_ms"],
    }

    payload = race.build_payload(
        "test", target, schedule_id, None, list(results.values())
    )
    path = race.save_results(tmp_path / "race_test.json", payload)
    tersimpan = json.loads(path.read_text(encoding="utf-8"))
    assert tersimpan["summary"]["menang"] == 1
    assert tersimpan["summary"]["konflik"] == 1
    assert len(tersimpan["rounds"]) == 2
