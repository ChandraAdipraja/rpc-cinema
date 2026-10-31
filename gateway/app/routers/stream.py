from __future__ import annotations

import json

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..services.cinema_gateway import get_gateway

router = APIRouter(prefix="/api")

_SSE_HEADERS = {
    "Cache-Control": "no-cache",
    "Connection": "keep-alive",
    "X-Accel-Buffering": "no",
}


def _to_sse(payload: dict) -> str:
    return f"data: {json.dumps(payload)}\n\n"


@router.get("/stream/kursi")
def stream_status_kursi(schedule_id: str):
    """SSE: meneruskan StreamStatusKursi (gRPC server streaming) satu jadwal ke browser."""

    def event_source():
        try:
            for update in get_gateway().stream_kursi(schedule_id):
                yield _to_sse(update)
        except Exception:
            # Koneksi client terputus atau gRPC error; stop stream.
            return

    return StreamingResponse(
        event_source(),
        media_type="text/event-stream",
        headers=_SSE_HEADERS,
    )
