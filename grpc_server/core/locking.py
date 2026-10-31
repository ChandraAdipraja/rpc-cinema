"""Lock bersama yang melindungi seluruh mutasi state server.

RLock dipakai supaya kode yang sudah memegang lock masih boleh memanggil
helper lain yang ikut mengunci (nested acquisition aman). Satu jenis lock
dipakai untuk kursi, reservasi, dan request ID agar operasi
check-and-update berjalan sebagai satu critical section utuh.
"""

import threading
from contextlib import contextmanager
from typing import Iterator


class StateLock:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    @contextmanager
    def hold(self) -> Iterator[threading.RLock]:
        with self._lock:
            yield self._lock

    @property
    def rlock(self) -> threading.RLock:
        return self._lock
