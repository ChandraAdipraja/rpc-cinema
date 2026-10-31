@echo off
rem Generate gRPC Python stubs dari cinema.proto
rem Jalankan dari root repo: scripts\generate_proto.bat
setlocal
cd /d "%~dp0.."

if not exist ".venv\Scripts\python.exe" (
    echo [ERROR] .venv tidak ditemukan. Buat dulu: python -m venv .venv ^&^& .venv\Scripts\python.exe -m pip install -r grpc_server\requirements.txt
    exit /b 1
)

if not exist "grpc_server\generated" mkdir "grpc_server\generated"
if not exist "gateway\app\grpc_client\generated" mkdir "gateway\app\grpc_client\generated"

.venv\Scripts\python.exe -m grpc_tools.protoc ^
    -Igrpc_server\proto ^
    --python_out=grpc_server\generated ^
    --grpc_python_out=grpc_server\generated ^
    --pyi_out=grpc_server\generated ^
    --python_out=gateway\app\grpc_client\generated ^
    --grpc_python_out=gateway\app\grpc_client\generated ^
    --pyi_out=gateway\app\grpc_client\generated ^
    grpc_server\proto\cinema.proto

if errorlevel 1 (
    echo [ERROR] Generate proto gagal.
    exit /b 1
)

echo [OK] Stub berhasil di-generate ke grpc_server\generated + gateway\app\grpc_client\generated:
dir /b grpc_server\generated
endlocal
