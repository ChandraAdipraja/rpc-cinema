#!/usr/bin/env bash
# Generate gRPC Python stubs dari cinema.proto
# Jalankan dari root repo: ./scripts/generate_proto.sh
set -euo pipefail
cd "$(dirname "$0")/.."

if [ ! -f ".venv/bin/python" ]; then
    echo "[ERROR] .venv tidak ditemukan. Buat dulu: python -m venv .venv && .venv/bin/python -m pip install -r grpc_server/requirements.txt"
    exit 1
fi

mkdir -p grpc_server/generated
mkdir -p gateway/app/grpc_client/generated

.venv/bin/python -m grpc_tools.protoc \
    -Igrpc_server/proto \
    --python_out=grpc_server/generated \
    --grpc_python_out=grpc_server/generated \
    --pyi_out=grpc_server/generated \
    --python_out=gateway/app/grpc_client/generated \
    --grpc_python_out=gateway/app/grpc_client/generated \
    --pyi_out=gateway/app/grpc_client/generated \
    grpc_server/proto/cinema.proto

echo "[OK] Stub berhasil di-generate ke grpc_server/generated + gateway/app/grpc_client/generated:"
ls grpc_server/generated
