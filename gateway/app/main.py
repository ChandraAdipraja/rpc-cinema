"""FastAPI Gateway Cinema.

Jembatan browser (React) <-> gRPC Server. Business logic tetap di server:
gateway hanya menerjemahkan HTTP <-> gRPC dan meneruskan stream.
Jalankan dari ROOT repo: .venv/Scripts/python.exe -m uvicorn gateway.app.main:app --host 127.0.0.1 --port 8000
"""

from __future__ import annotations

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import kursi, pesanan, stream

GATEWAY_TITLE = "Cinema RPC Gateway"
GATEWAY_VERSION = "0.1.0"

# Frontend dev server Vite; list bisa diperluas lewat env CORS_ORIGINS (dipisah koma).
_DEFAULT_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"


def create_app() -> FastAPI:
    app = FastAPI(title=GATEWAY_TITLE, version=GATEWAY_VERSION)

    origins = os.getenv("CORS_ORIGINS", _DEFAULT_ORIGINS).split(",")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[origin.strip() for origin in origins],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(kursi.router)
    app.include_router(pesanan.router)
    app.include_router(stream.router)

    @app.get("/api/health")
    def health():
        # Health check transport-level; kesiapan gRPC dicek endpoint lain saat dipakai.
        return {"status": "ok", "service": GATEWAY_TITLE, "version": GATEWAY_VERSION}

    return app


app = create_app()
