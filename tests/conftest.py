"""Fixture pytest: menjalankan satu instance gRPC server per module test."""

from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import grpc
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "grpc_server") not in sys.path:
    sys.path.insert(0, str(ROOT / "grpc_server"))

from cinema_client import CinemaRpcClient  # noqa: E402


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


@dataclass
class ServerHandle:
    process: subprocess.Popen
    port: int
    client: CinemaRpcClient


@pytest.fixture(scope="module")
def server():
    port = _free_port()
    process = subprocess.Popen(
        [sys.executable, str(ROOT / "grpc_server" / "server.py")],
        env={**os.environ, "GRPC_PORT": str(port)},
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    client = CinemaRpcClient(
        target=f"localhost:{port}",
        timeout=5.0,
        max_retries=6,
        backoff_base=0.1,
    )

    deadline = time.time() + 15.0
    ready = False
    while time.time() < deadline:
        try:
            client.lihat_daftar_jadwal()
            ready = True
            break
        except grpc.RpcError:
            time.sleep(0.2)

    if not ready:
        client.close()
        process.terminate()
        pytest.fail("gRPC server tidak siap dalam batas waktu")

    handle = ServerHandle(process=process, port=port, client=client)
    yield handle

    client.close()
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
