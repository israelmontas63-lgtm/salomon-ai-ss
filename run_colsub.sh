#!/usr/bin/env bash
# run_colsub.sh — Branch de Control Autónomo (BCA)
# Detecta cambios en el código, mata :8000 y reinicia Colsub sin intervención.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"
PORT="${COLSUB_PORT:-8000}"

echo "[run_colsub] Colsub BCA · raíz=$ROOT · puerto=$PORT"

# Preferir Python del venv si existe
if [[ -x "$ROOT/.venv/Scripts/python.exe" ]]; then
  PY="$ROOT/.venv/Scripts/python.exe"
elif [[ -x "$ROOT/.venv/bin/python" ]]; then
  PY="$ROOT/.venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
  PY="python3"
else
  PY="python"
fi

# Asegurar watchdog
"$PY" -c "import watchdog" 2>/dev/null || "$PY" -m pip install -q watchdog psutil

kill_port() {
  local p="$1"
  if command -v lsof >/dev/null 2>&1; then
    lsof -ti ":$p" 2>/dev/null | xargs -r kill -9 2>/dev/null || true
  elif command -v fuser >/dev/null 2>&1; then
    fuser -k "${p}/tcp" 2>/dev/null || true
  elif command -v powershell.exe >/dev/null 2>&1; then
    powershell.exe -NoProfile -Command \
      "Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id \$_.OwningProcess -Force -ErrorAction SilentlyContinue }" \
      2>/dev/null || true
  fi
}

echo "[run_colsub] Liberando puerto $PORT…"
kill_port "$PORT"
sleep 0.5

export BCA_MODE=1
export COLSUB_PORT="$PORT"
export COLSUB_HOST="${COLSUB_HOST:-0.0.0.0}"
export TUNEL_HABILITADO="${TUNEL_HABILITADO:-true}"
export TUNEL_AUTO="${TUNEL_AUTO:-true}"

echo "[run_colsub] host=0.0.0.0 · túnel localtunnel auto=$TUNEL_AUTO"
echo "[run_colsub] Al arrancar verás la Public URL para el teléfono."

exec "$PY" -m cognicion.orquesta.bca
