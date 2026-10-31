"""Loader untuk stub gRPC hasil generate.

Mengatur sys.path agar folder generated dapat mengimpor cinema_pb2
dan cinema_pb2_grpc sebagai modul biasa, lalu mengekspor keduanya.
"""

from pathlib import Path
import sys

_GENERATED_DIR = str(Path(__file__).resolve().parent / "generated")
if _GENERATED_DIR not in sys.path:
    sys.path.insert(0, _GENERATED_DIR)

import cinema_pb2  # noqa: E402
import cinema_pb2_grpc  # noqa: E402

__all__ = ["cinema_pb2", "cinema_pb2_grpc"]
